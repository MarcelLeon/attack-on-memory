"""Static policy linting and paired what-if change analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from attack_on_memory.domain.models import RetrievedMemory, Sensitivity, TaskIntent
from attack_on_memory.governance.policies import DisclosurePolicy


@dataclass(frozen=True)
class PolicyLintFinding:
    severity: Literal["error", "warning"]
    code: str
    policy_id: str
    policy_version: int
    role: str
    message: str


@dataclass(frozen=True)
class PolicyDecisionSample:
    item: RetrievedMemory
    intent: TaskIntent


@dataclass(frozen=True)
class PolicyDecisionChange:
    request_id: str
    atom_id: str
    before_allowed: bool
    after_allowed: bool
    before_reason: str
    after_reason: str


@dataclass(frozen=True)
class PolicyChangeReport:
    policy_id: str
    from_version: int
    to_version: int
    sample_count: int
    changes: tuple[PolicyDecisionChange, ...]

    @property
    def newly_allowed(self) -> tuple[PolicyDecisionChange, ...]:
        return tuple(
            item
            for item in self.changes
            if not item.before_allowed and item.after_allowed
        )

    @property
    def newly_denied(self) -> tuple[PolicyDecisionChange, ...]:
        return tuple(
            item
            for item in self.changes
            if item.before_allowed and not item.after_allowed
        )


def lint_policy(policy: DisclosurePolicy) -> tuple[PolicyLintFinding, ...]:
    """Return stable, content-free findings for one disclosure policy."""
    findings: list[PolicyLintFinding] = []

    def add(severity: Literal["error", "warning"], code: str, message: str) -> None:
        findings.append(
            PolicyLintFinding(
                severity=severity,
                code=code,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                role=policy.role,
                message=message,
            )
        )

    if policy.policy_id == "default-disclosure":
        add("warning", "identity.default", "assign a deployment-specific policy_id")
    if not policy.allowed_domains:
        add("warning", "domain.wildcard", "policy allows every domain")
    if not policy.allowed_tasks:
        add("warning", "task.wildcard", "policy allows every task")
    if policy.require_explicit_purpose and not policy.allowed_purposes:
        add(
            "error",
            "purpose.explicit_without_allowlist",
            "explicit purpose is required but every non-empty purpose is accepted",
        )
    elif policy.allowed_purposes and not policy.require_explicit_purpose:
        add(
            "warning",
            "purpose.legacy_fallback",
            "task may substitute for a missing explicit purpose",
        )
    elif not policy.allowed_purposes:
        add("warning", "purpose.unbound", "policy is not purpose-bound")
    if policy.max_sensitivity is Sensitivity.SECRET:
        add("warning", "sensitivity.secret", "policy can project secret memories")
    if policy.min_confidence == 0.0:
        add("warning", "confidence.zero", "policy accepts zero-confidence memories")
    return tuple(findings)


def lint_policy_set(
    policies: Iterable[DisclosurePolicy],
) -> tuple[PolicyLintFinding, ...]:
    """Lint policies and detect ambiguous role or identity registrations."""
    items = tuple(policies)
    findings = [finding for policy in items for finding in lint_policy(policy)]
    roles: dict[str, list[DisclosurePolicy]] = {}
    identities: dict[tuple[str, int], list[DisclosurePolicy]] = {}
    for policy in items:
        roles.setdefault(policy.role, []).append(policy)
        identities.setdefault((policy.policy_id, policy.version), []).append(policy)
    for role, duplicates in roles.items():
        if len(duplicates) > 1:
            first = duplicates[0]
            findings.append(
                PolicyLintFinding(
                    severity="error",
                    code="registration.duplicate_role",
                    policy_id=first.policy_id,
                    policy_version=first.version,
                    role=role,
                    message="multiple active policies target the same role",
                )
            )
    for (policy_id, version), duplicates in identities.items():
        if len(duplicates) > 1:
            first = duplicates[0]
            findings.append(
                PolicyLintFinding(
                    severity="error",
                    code="identity.duplicate_version",
                    policy_id=policy_id,
                    policy_version=version,
                    role=first.role,
                    message="policy identity/version must be globally unique",
                )
            )
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                item.severity != "error",
                item.code,
                item.policy_id,
                item.policy_version,
                item.role,
            ),
        )
    )


def compare_policy_change(
    current: DisclosurePolicy,
    candidate: DisclosurePolicy,
    samples: Iterable[PolicyDecisionSample],
) -> PolicyChangeReport:
    """Compare versions on identical labeled decisions without exposing claims."""
    if current.role != candidate.role or current.policy_id != candidate.policy_id:
        raise ValueError("policy what-if comparison requires the same role and policy_id")
    if candidate.version != current.version + 1:
        raise ValueError("candidate policy version must increment by exactly one")
    sample_items = tuple(samples)
    changes: list[PolicyDecisionChange] = []
    seen_keys: set[tuple[str, str]] = set()
    for sample in sample_items:
        if sample.intent.role != current.role:
            raise ValueError("sample intent role does not match compared policy")
        key = (sample.intent.request_id, sample.item.atom.id)
        if key in seen_keys:
            raise ValueError(f"duplicate what-if sample key: {key}")
        seen_keys.add(key)
        before_allowed, before_reason = current.decide(sample.item, sample.intent)
        after_allowed, after_reason = candidate.decide(sample.item, sample.intent)
        if (before_allowed, before_reason) == (after_allowed, after_reason):
            continue
        changes.append(
            PolicyDecisionChange(
                request_id=sample.intent.request_id,
                atom_id=sample.item.atom.id,
                before_allowed=before_allowed,
                after_allowed=after_allowed,
                before_reason=before_reason,
                after_reason=after_reason,
            )
        )
    return PolicyChangeReport(
        policy_id=current.policy_id,
        from_version=current.version,
        to_version=candidate.version,
        sample_count=len(sample_items),
        changes=tuple(changes),
    )


def assert_no_permission_expansion(report: PolicyChangeReport) -> None:
    """Fail a rollout gate when a candidate newly allows any sampled memory."""
    if not report.newly_allowed:
        return
    keys = sorted(
        (item.request_id, item.atom_id) for item in report.newly_allowed
    )
    raise PermissionError(f"policy change expands disclosure for samples: {keys}")
