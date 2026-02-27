"""Scenario spec validation for simulation runner inputs."""

from __future__ import annotations

from typing import Any, Mapping

ALLOWED_SENSITIVITY = {"public", "internal", "restricted", "secret"}
ALLOWED_EDGE_TYPES = {
    "supports",
    "contradicts",
    "derived_from",
    "inherited_from",
    "caused_by",
}
ALLOWED_BRANCH_STATUS = {"active", "merged", "rejected", "archived"}
ALLOWED_COMPARISON_OP = {"==", "!=", ">", ">=", "<", "<="}
ALLOWED_METRICS = {
    "hit_rate",
    "task_success_rate",
    "repeat_error_rate",
    "conflict_rate",
    "contamination_rate",
    "avg_latency_ms",
    "avg_token_cost",
}


def validate_scenario_spec(spec: Mapping[str, Any]) -> list[str]:
    """Return validation errors for a scenario spec."""
    errors: list[str] = []

    _require_non_empty_str(spec, "schema_version", errors, ctx="scenario")
    _require_non_empty_str(spec, "scenario_id", errors, ctx="scenario")

    variants = spec.get("variants")
    if not isinstance(variants, list) or not variants:
        errors.append("scenario.variants must be a non-empty list")
        return errors

    variant_ids: set[str] = set()
    for idx, variant in enumerate(variants):
        ctx = f"scenario.variants[{idx}]"
        if not isinstance(variant, Mapping):
            errors.append(f"{ctx} must be an object")
            continue

        variant_id = _require_non_empty_str(variant, "variant_id", errors, ctx=ctx)
        if variant_id:
            if variant_id in variant_ids:
                errors.append(f"duplicate variant_id '{variant_id}'")
            variant_ids.add(variant_id)

        memory_ids = _validate_variant_memories(variant, errors, ctx=ctx)
        _validate_variant_policies(variant, errors, ctx=ctx)
        _validate_variant_edges(variant, memory_ids, errors, ctx=ctx)
        branches = _validate_variant_branches(variant, errors, ctx=ctx)
        _validate_variant_branch_evaluations(variant, branches, errors, ctx=ctx)
        _validate_variant_events(variant, memory_ids, errors, ctx=ctx)
        _validate_variant_metric_assertions(variant, errors, ctx=ctx)

    return errors


def ensure_valid_scenario_spec(spec: Mapping[str, Any]) -> None:
    """Raise ValueError if the scenario spec is invalid."""
    errors = validate_scenario_spec(spec)
    if not errors:
        return
    message = "Invalid scenario spec:\n- " + "\n- ".join(errors)
    raise ValueError(message)


def _validate_variant_memories(
    variant: Mapping[str, Any],
    errors: list[str],
    *,
    ctx: str,
) -> set[str]:
    memories = variant.get("memories")
    if not isinstance(memories, list) or not memories:
        errors.append(f"{ctx}.memories must be a non-empty list")
        return set()

    memory_ids: set[str] = set()
    for idx, memory in enumerate(memories):
        mctx = f"{ctx}.memories[{idx}]"
        if not isinstance(memory, Mapping):
            errors.append(f"{mctx} must be an object")
            continue

        mem_id = _require_non_empty_str(memory, "id", errors, ctx=mctx)
        if mem_id:
            if mem_id in memory_ids:
                errors.append(f"duplicate memory id '{mem_id}' in {ctx}")
            memory_ids.add(mem_id)

        _require_non_empty_str(memory, "claim", errors, ctx=mctx)
        _require_non_empty_str(memory, "source_agent", errors, ctx=mctx)
        _require_confidence(memory, "confidence", errors, ctx=mctx)
        _require_number(memory, "age_days", errors, ctx=mctx, minimum=0)
        _require_number(memory, "ttl_days", errors, ctx=mctx, minimum=0.001)

        sensitivity = _require_non_empty_str(memory, "sensitivity", errors, ctx=mctx)
        if sensitivity and sensitivity not in ALLOWED_SENSITIVITY:
            errors.append(f"{mctx}.sensitivity must be one of {sorted(ALLOWED_SENSITIVITY)}")

        scope = memory.get("scope")
        if not isinstance(scope, Mapping):
            errors.append(f"{mctx}.scope must be an object")
        else:
            _require_non_empty_str(scope, "domain", errors, ctx=f"{mctx}.scope")
            _require_non_empty_str(scope, "task", errors, ctx=f"{mctx}.scope")

        evidence = memory.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{mctx}.evidence must be a non-empty list")
        else:
            for eidx, entry in enumerate(evidence):
                ectx = f"{mctx}.evidence[{eidx}]"
                if not isinstance(entry, Mapping):
                    errors.append(f"{ectx} must be an object")
                    continue
                _require_non_empty_str(entry, "ref", errors, ctx=ectx)
                _require_non_empty_str(entry, "source", errors, ctx=ectx)
                _require_number(entry, "age_days", errors, ctx=ectx, minimum=0)

    return memory_ids


def _validate_variant_policies(
    variant: Mapping[str, Any],
    errors: list[str],
    *,
    ctx: str,
) -> None:
    policies = variant.get("policies")
    if not isinstance(policies, list) or not policies:
        errors.append(f"{ctx}.policies must be a non-empty list")
        return

    roles: set[str] = set()
    for idx, policy in enumerate(policies):
        pctx = f"{ctx}.policies[{idx}]"
        if not isinstance(policy, Mapping):
            errors.append(f"{pctx} must be an object")
            continue

        role = _require_non_empty_str(policy, "role", errors, ctx=pctx)
        if role:
            if role in roles:
                errors.append(f"duplicate policy role '{role}' in {ctx}")
            roles.add(role)

        sensitivity = _require_non_empty_str(policy, "max_sensitivity", errors, ctx=pctx)
        if sensitivity and sensitivity not in ALLOWED_SENSITIVITY:
            errors.append(f"{pctx}.max_sensitivity must be one of {sorted(ALLOWED_SENSITIVITY)}")

        min_conf = policy.get("min_confidence")
        if not isinstance(min_conf, (int, float)):
            errors.append(f"{pctx}.min_confidence must be a number")
        elif min_conf < 0 or min_conf > 1:
            errors.append(f"{pctx}.min_confidence must be between 0 and 1")

        for key in ("allowed_domains", "allowed_tasks"):
            value = policy.get(key)
            if not isinstance(value, list) or not value:
                errors.append(f"{pctx}.{key} must be a non-empty list")
                continue
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{pctx}.{key} contains invalid value '{item}'")


def _validate_variant_edges(
    variant: Mapping[str, Any],
    memory_ids: set[str],
    errors: list[str],
    *,
    ctx: str,
) -> None:
    edges = variant.get("edges", [])
    if not isinstance(edges, list):
        errors.append(f"{ctx}.edges must be a list when provided")
        return

    for idx, edge in enumerate(edges):
        ectx = f"{ctx}.edges[{idx}]"
        if not isinstance(edge, Mapping):
            errors.append(f"{ectx} must be an object")
            continue
        source_id = _require_non_empty_str(edge, "source_id", errors, ctx=ectx)
        target_id = _require_non_empty_str(edge, "target_id", errors, ctx=ectx)
        edge_type = _require_non_empty_str(edge, "edge_type", errors, ctx=ectx)
        _require_number(edge, "weight", errors, ctx=ectx, minimum=0.000001, required=False)

        if edge_type and edge_type not in ALLOWED_EDGE_TYPES:
            errors.append(f"{ectx}.edge_type must be one of {sorted(ALLOWED_EDGE_TYPES)}")
        if source_id and source_id not in memory_ids:
            errors.append(f"{ectx}.source_id '{source_id}' not found in memories")
        if target_id and target_id not in memory_ids:
            errors.append(f"{ectx}.target_id '{target_id}' not found in memories")


def _validate_variant_branches(
    variant: Mapping[str, Any],
    errors: list[str],
    *,
    ctx: str,
) -> set[str]:
    branches = variant.get("branches", [])
    if not isinstance(branches, list):
        errors.append(f"{ctx}.branches must be a list when provided")
        return set()

    branch_ids: set[str] = set()
    for idx, branch in enumerate(branches):
        bctx = f"{ctx}.branches[{idx}]"
        if not isinstance(branch, Mapping):
            errors.append(f"{bctx} must be an object")
            continue
        branch_id = _require_non_empty_str(branch, "id", errors, ctx=bctx)
        if branch_id:
            if branch_id in branch_ids:
                errors.append(f"duplicate branch id '{branch_id}' in {ctx}")
            branch_ids.add(branch_id)
        _require_non_empty_str(branch, "name", errors, ctx=bctx)
        _require_non_empty_str(branch, "hypothesis", errors, ctx=bctx)
        status = _require_non_empty_str(branch, "status", errors, ctx=bctx)
        if status and status not in ALLOWED_BRANCH_STATUS:
            errors.append(f"{bctx}.status must be one of {sorted(ALLOWED_BRANCH_STATUS)}")

    return branch_ids


def _validate_variant_branch_evaluations(
    variant: Mapping[str, Any],
    branches: set[str],
    errors: list[str],
    *,
    ctx: str,
) -> None:
    evaluations = variant.get("branch_evaluations", [])
    if not isinstance(evaluations, list):
        errors.append(f"{ctx}.branch_evaluations must be a list when provided")
        return

    evaluation_branch_ids: set[str] = set()
    for idx, entry in enumerate(evaluations):
        ectx = f"{ctx}.branch_evaluations[{idx}]"
        if not isinstance(entry, Mapping):
            errors.append(f"{ectx} must be an object")
            continue

        branch_id = _require_non_empty_str(entry, "branch_id", errors, ctx=ectx)
        if branch_id:
            evaluation_branch_ids.add(branch_id)
            if branches and branch_id not in branches:
                errors.append(f"{ectx}.branch_id '{branch_id}' not declared in branches")

        _require_confidence(entry, "success_rate", errors, ctx=ectx)
        _require_confidence(entry, "risk_score", errors, ctx=ectx)
        _require_confidence(entry, "cost_score", errors, ctx=ectx)

    expected_top = variant.get("expected_top_branch")
    if expected_top is not None:
        if not isinstance(expected_top, str) or not expected_top.strip():
            errors.append(f"{ctx}.expected_top_branch must be a non-empty string")
        elif evaluations and expected_top not in evaluation_branch_ids:
            errors.append(
                f"{ctx}.expected_top_branch '{expected_top}' not found in branch_evaluations"
            )


def _validate_variant_events(
    variant: Mapping[str, Any],
    memory_ids: set[str],
    errors: list[str],
    *,
    ctx: str,
) -> None:
    events = variant.get("events")
    if not isinstance(events, list) or not events:
        errors.append(f"{ctx}.events must be a non-empty list")
        return

    policy_roles = {
        policy.get("role")
        for policy in variant.get("policies", [])
        if isinstance(policy, Mapping)
    }

    event_ids: set[str] = set()
    for idx, event in enumerate(events):
        ectx = f"{ctx}.events[{idx}]"
        if not isinstance(event, Mapping):
            errors.append(f"{ectx} must be an object")
            continue

        event_id = _require_non_empty_str(event, "event_id", errors, ctx=ectx)
        if event_id:
            if event_id in event_ids:
                errors.append(f"duplicate event_id '{event_id}' in {ctx}")
            event_ids.add(event_id)

        role = _require_non_empty_str(event, "role", errors, ctx=ectx)
        if role and role not in policy_roles:
            errors.append(f"{ectx}.role '{role}' has no matching policy")

        _require_non_empty_str(event, "actor", errors, ctx=ectx)
        _require_non_empty_str(event, "domain", errors, ctx=ectx)
        _require_non_empty_str(event, "task", errors, ctx=ectx)
        _require_non_empty_str(event, "objective", errors, ctx=ectx)

        _require_number(event, "top_k", errors, ctx=ectx, minimum=1)
        _require_number(event, "graph_hops", errors, ctx=ectx, minimum=0)
        lookback = event.get("lookback_days")
        if lookback is not None and not isinstance(lookback, (int, float)):
            errors.append(f"{ectx}.lookback_days must be a number or null")

        seed_ids = event.get("seed_memory_ids", [])
        if not isinstance(seed_ids, list):
            errors.append(f"{ectx}.seed_memory_ids must be a list when provided")
        else:
            for seed_id in seed_ids:
                if not isinstance(seed_id, str) or not seed_id.strip():
                    errors.append(f"{ectx}.seed_memory_ids contains invalid id '{seed_id}'")
                elif memory_ids and seed_id not in memory_ids:
                    errors.append(f"{ectx}.seed_memory_id '{seed_id}' not found in memories")

        expected = event.get("expected", {})
        if expected is not None and not isinstance(expected, Mapping):
            errors.append(f"{ectx}.expected must be an object when provided")
        elif isinstance(expected, Mapping):
            for key in ("must_include", "must_exclude", "must_have_citation", "must_not_cite"):
                values = expected.get(key, [])
                if not isinstance(values, list):
                    errors.append(f"{ectx}.expected.{key} must be a list when provided")
                    continue
                for value in values:
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"{ectx}.expected.{key} has invalid id '{value}'")
                    elif memory_ids and value not in memory_ids:
                        errors.append(f"{ectx}.expected.{key} id '{value}' not found in memories")

            for count_key in ("min_memories", "max_memories", "min_redacted", "max_redacted"):
                count_value = expected.get(count_key)
                if count_value is not None:
                    _require_number(expected, count_key, errors, ctx=f"{ectx}.expected", minimum=0)

        outcome = event.get("outcome")
        if outcome is not None and not isinstance(outcome, Mapping):
            errors.append(f"{ectx}.outcome must be an object when provided")
        elif isinstance(outcome, Mapping):
            success = outcome.get("success")
            if not isinstance(success, bool):
                errors.append(f"{ectx}.outcome.success must be boolean")
            _require_number(outcome, "latency_ms", errors, ctx=f"{ectx}.outcome", minimum=0)
            _require_number(outcome, "token_cost", errors, ctx=f"{ectx}.outcome", minimum=0)
            for bool_key in ("conflict", "contamination"):
                value = outcome.get(bool_key)
                if not isinstance(value, bool):
                    errors.append(f"{ectx}.outcome.{bool_key} must be boolean")


def _validate_variant_metric_assertions(
    variant: Mapping[str, Any],
    errors: list[str],
    *,
    ctx: str,
) -> None:
    assertions = variant.get("metric_assertions", [])
    if not isinstance(assertions, list):
        errors.append(f"{ctx}.metric_assertions must be a list when provided")
        return

    for idx, assertion in enumerate(assertions):
        actx = f"{ctx}.metric_assertions[{idx}]"
        if not isinstance(assertion, Mapping):
            errors.append(f"{actx} must be an object")
            continue
        metric = _require_non_empty_str(assertion, "metric", errors, ctx=actx)
        if metric and metric not in ALLOWED_METRICS:
            errors.append(f"{actx}.metric must be one of {sorted(ALLOWED_METRICS)}")
        op = _require_non_empty_str(assertion, "op", errors, ctx=actx)
        if op and op not in ALLOWED_COMPARISON_OP:
            errors.append(f"{actx}.op must be one of {sorted(ALLOWED_COMPARISON_OP)}")
        _require_number(assertion, "value", errors, ctx=actx)


def _require_non_empty_str(
    mapping: Mapping[str, Any],
    key: str,
    errors: list[str],
    *,
    ctx: str,
) -> str | None:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{ctx}.{key} must be a non-empty string")
        return None
    return value.strip()


def _require_confidence(
    mapping: Mapping[str, Any],
    key: str,
    errors: list[str],
    *,
    ctx: str,
) -> None:
    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        errors.append(f"{ctx}.{key} must be a number")
        return
    if value < 0 or value > 1:
        errors.append(f"{ctx}.{key} must be between 0 and 1")


def _require_number(
    mapping: Mapping[str, Any],
    key: str,
    errors: list[str],
    *,
    ctx: str,
    minimum: float | None = None,
    required: bool = True,
) -> None:
    if key not in mapping:
        if required:
            errors.append(f"{ctx}.{key} is required")
        return

    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        errors.append(f"{ctx}.{key} must be a number")
        return
    if minimum is not None and float(value) < minimum:
        errors.append(f"{ctx}.{key} must be >= {minimum}")
