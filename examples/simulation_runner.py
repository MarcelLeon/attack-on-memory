"""Scenario simulation runner for Attack on Memory examples.

This runner executes scenario specs in JSON and validates expected behavior
for retrieval, selective disclosure, branch ranking, and metrics.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from attack_on_memory.application.branch_world_model import BranchEvaluation, BranchWorldModelService
from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.domain.models import (
    BranchStatus,
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryScope,
    Sensitivity,
    utc_now,
)
from attack_on_memory.evals.metrics import EvalTracker
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.runtime.context import ContextAssembler
from attack_on_memory.runtime.openclaw_adapter import OpenClawMemoryAdapter, OpenClawTaskEvent
from attack_on_memory.scenarios.spec_validation import ensure_valid_scenario_spec


@dataclass
class EventResult:
    event_id: str
    passed: bool
    memory_ids: list[str] = field(default_factory=list)
    citation_ids: list[str] = field(default_factory=list)
    redacted: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class VariantResult:
    scenario_id: str
    variant_id: str
    passed: bool
    event_results: list[EventResult]
    metric_snapshot: dict[str, float]
    branch_ranks: list[dict[str, float]]
    failures: list[str] = field(default_factory=list)


def _build_adapter(
    variant: dict[str, Any],
    now,
) -> tuple[OpenClawMemoryAdapter, BranchWorldModelService, InMemoryStore]:
    store = InMemoryStore()
    capture_service = CaptureService(store)
    retrieval_service = RetrievalService(store)

    governor = MemoryGovernor()
    for raw_policy in variant.get("policies", []):
        governor.register_policy(
            DisclosurePolicy(
                role=raw_policy["role"],
                max_sensitivity=Sensitivity(raw_policy.get("max_sensitivity", "internal")),
                allowed_domains=frozenset(raw_policy.get("allowed_domains", [])),
                allowed_tasks=frozenset(raw_policy.get("allowed_tasks", [])),
                min_confidence=float(raw_policy.get("min_confidence", 0.0)),
            )
        )

    assembler = ContextAssembler(retrieval_service, governor)
    tracker = EvalTracker()
    adapter = OpenClawMemoryAdapter(
        context_assembler=assembler,
        capture_service=capture_service,
        tracker=tracker,
    )

    for raw_memory in variant.get("memories", []):
        capture_service.capture(_build_memory_atom(raw_memory, now))

    for raw_edge in variant.get("edges", []):
        store.add_edge(
            MemoryEdge(
                source_id=raw_edge["source_id"],
                target_id=raw_edge["target_id"],
                edge_type=EdgeType(raw_edge["edge_type"]),
                weight=float(raw_edge.get("weight", 1.0)),
            )
        )

    branch_service = BranchWorldModelService(store)
    for raw_branch in variant.get("branches", []):
        branch_service.create_branch(
            branch_id=raw_branch["id"],
            name=raw_branch["name"],
            hypothesis=raw_branch["hypothesis"],
            parent_id=raw_branch.get("parent_id"),
            created_at=now,
        )
        status = BranchStatus(raw_branch.get("status", "active"))
        if status != BranchStatus.ACTIVE:
            branch_service.update_status(raw_branch["id"], status)

    return adapter, branch_service, store


def _build_memory_atom(raw_memory: dict[str, Any], now) -> MemoryAtom:
    age_days = float(raw_memory.get("age_days", 0.0))
    ttl_days = float(raw_memory.get("ttl_days", 30.0))
    created_at = now - timedelta(days=age_days)

    raw_scope = raw_memory["scope"]
    scope = MemoryScope(
        domain=raw_scope["domain"],
        task=raw_scope["task"],
        owner=raw_scope.get("owner", "shared"),
    )

    raw_evidence = raw_memory.get("evidence", [])
    if not raw_evidence:
        raw_evidence = [
            {
                "ref": f"auto:{raw_memory['id']}",
                "source": "scenario",
                "age_days": age_days,
            }
        ]

    evidence = tuple(
        Evidence(
            ref=entry["ref"],
            source=entry["source"],
            captured_at=now - timedelta(days=float(entry.get("age_days", age_days))),
            note=entry.get("note"),
        )
        for entry in raw_evidence
    )

    return MemoryAtom(
        id=raw_memory["id"],
        claim=raw_memory["claim"],
        evidence=evidence,
        source_agent=raw_memory["source_agent"],
        confidence=float(raw_memory["confidence"]),
        scope=scope,
        created_at=created_at,
        ttl=timedelta(days=ttl_days),
        branch_id=raw_memory.get("branch_id", "main"),
        sensitivity=Sensitivity(raw_memory.get("sensitivity", "internal")),
        tags=tuple(raw_memory.get("tags", [])),
        metadata=raw_memory.get("metadata", {}),
    )


def _evaluate_event(packet, expected: dict[str, Any]) -> EventResult:
    memory_ids = sorted(item.atom_id for item in packet.memories)
    citation_ids = sorted(citation.atom_id for citation in packet.citations)
    memory_set = set(memory_ids)
    citation_set = set(citation_ids)
    failures: list[str] = []

    for atom_id in expected.get("must_include", []):
        if atom_id not in memory_set:
            failures.append(f"expected memory '{atom_id}' to be included")

    for atom_id in expected.get("must_exclude", []):
        if atom_id in memory_set:
            failures.append(f"expected memory '{atom_id}' to be excluded")

    for atom_id in expected.get("must_have_citation", []):
        if atom_id not in citation_set:
            failures.append(f"expected citation '{atom_id}' to be present")

    for atom_id in expected.get("must_not_cite", []):
        if atom_id in citation_set:
            failures.append(f"expected citation '{atom_id}' to be absent")

    min_memories = expected.get("min_memories")
    if min_memories is not None and len(memory_ids) < int(min_memories):
        failures.append(
            f"expected at least {int(min_memories)} memories, got {len(memory_ids)}"
        )

    max_memories = expected.get("max_memories")
    if max_memories is not None and len(memory_ids) > int(max_memories):
        failures.append(
            f"expected at most {int(max_memories)} memories, got {len(memory_ids)}"
        )

    redacted = int(packet.diagnostics.get("redacted", 0))
    min_redacted = expected.get("min_redacted")
    if min_redacted is not None and redacted < int(min_redacted):
        failures.append(f"expected redacted >= {int(min_redacted)}, got {redacted}")

    max_redacted = expected.get("max_redacted")
    if max_redacted is not None and redacted > int(max_redacted):
        failures.append(f"expected redacted <= {int(max_redacted)}, got {redacted}")

    return EventResult(
        event_id=packet.request_id,
        passed=not failures,
        memory_ids=memory_ids,
        citation_ids=citation_ids,
        redacted=redacted,
        failures=failures,
    )


def _apply_outcome(adapter: OpenClawMemoryAdapter, raw_outcome: dict[str, Any] | None) -> None:
    if not raw_outcome:
        return

    adapter.record_outcome(
        success=bool(raw_outcome.get("success", False)),
        latency_ms=float(raw_outcome.get("latency_ms", 0.0)),
        token_cost=float(raw_outcome.get("token_cost", 0.0)),
        error_signature=raw_outcome.get("error_signature"),
        conflict=bool(raw_outcome.get("conflict", False)),
        contamination=bool(raw_outcome.get("contamination", False)),
    )


def _evaluate_metric_assertions(
    metric_snapshot: dict[str, float],
    metric_assertions: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    for assertion in metric_assertions:
        metric = assertion["metric"]
        expected = float(assertion["value"])
        op = assertion.get("op", ">=")
        actual = metric_snapshot.get(metric)
        if actual is None:
            failures.append(f"unknown metric '{metric}'")
            continue
        if not _compare(actual, op, expected):
            failures.append(
                f"metric assertion failed: {metric} {op} {expected:.4f}, actual {actual:.4f}"
            )
    return failures


def _compare(actual: float, op: str, expected: float) -> bool:
    if op == "==":
        return abs(actual - expected) < 1e-9
    if op == "!=":
        return abs(actual - expected) >= 1e-9
    if op == ">":
        return actual > expected
    if op == ">=":
        return actual >= expected
    if op == "<":
        return actual < expected
    if op == "<=":
        return actual <= expected
    raise ValueError(f"Unsupported operator: {op}")


def _run_variant(scenario_id: str, variant: dict[str, Any]) -> VariantResult:
    now = utc_now()
    adapter, branch_service, _ = _build_adapter(variant, now)

    event_results: list[EventResult] = []
    failures: list[str] = []

    for raw_event in variant.get("events", []):
        task_event = OpenClawTaskEvent(
            task_id=raw_event["event_id"],
            actor=raw_event["actor"],
            role=raw_event["role"],
            domain=raw_event["domain"],
            task=raw_event["task"],
            objective=raw_event["objective"],
            branch_id=raw_event.get("branch_id", "main"),
            seed_memory_ids=tuple(raw_event.get("seed_memory_ids", [])),
        )
        packet = adapter.build_context(
            task_event,
            at=now,
            top_k=int(raw_event.get("top_k", 5)),
            lookback_days=raw_event.get("lookback_days", 30),
            graph_hops=int(raw_event.get("graph_hops", 1)),
        )

        result = _evaluate_event(packet, raw_event.get("expected", {}))
        if not result.passed:
            failures.extend([f"event {result.event_id}: {issue}" for issue in result.failures])
        event_results.append(result)
        _apply_outcome(adapter, raw_event.get("outcome"))

    branch_ranks: list[dict[str, float]] = []
    raw_evaluations = variant.get("branch_evaluations", [])
    if raw_evaluations:
        evaluations = [
            BranchEvaluation(
                branch_id=entry["branch_id"],
                success_rate=float(entry["success_rate"]),
                risk_score=float(entry["risk_score"]),
                cost_score=float(entry["cost_score"]),
            )
            for entry in raw_evaluations
        ]
        ranks = branch_service.rank_branches(
            evaluations,
            risk_weight=float(variant.get("risk_weight", 0.20)),
            cost_weight=float(variant.get("cost_weight", 0.15)),
        )
        branch_ranks = [
            {"branch_id": rank.branch_id, "utility": rank.utility} for rank in ranks
        ]
        expected_top = variant.get("expected_top_branch")
        if expected_top and (not ranks or ranks[0].branch_id != expected_top):
            top = ranks[0].branch_id if ranks else "<none>"
            failures.append(
                f"expected top branch '{expected_top}', got '{top}'"
            )

    metric_snapshot = adapter.metrics_snapshot()
    failures.extend(
        _evaluate_metric_assertions(metric_snapshot, variant.get("metric_assertions", []))
    )

    return VariantResult(
        scenario_id=scenario_id,
        variant_id=variant["variant_id"],
        passed=not failures,
        event_results=event_results,
        metric_snapshot=metric_snapshot,
        branch_ranks=branch_ranks,
        failures=failures,
    )


def run_scenario(spec: dict[str, Any]) -> list[VariantResult]:
    scenario_id = spec["scenario_id"]
    variants = spec.get("variants", [])
    if not variants:
        raise ValueError(f"Scenario '{scenario_id}' has no variants")
    return [_run_variant(scenario_id, variant) for variant in variants]


def _collect_scenario_files(args: argparse.Namespace) -> list[Path]:
    if args.scenarios:
        return [Path(path).resolve() for path in args.scenarios]

    scenario_dir = Path(args.scenarios_dir).resolve()
    return sorted(
        path
        for path in scenario_dir.glob("*.json")
        if not path.name.endswith(".schema.json")
    )


def _print_results(results: list[VariantResult]) -> None:
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.scenario_id}::{result.variant_id}")
        for event in result.event_results:
            event_status = "PASS" if event.passed else "FAIL"
            print(
                "  "
                f"- {event.event_id}: {event_status} "
                f"memories={event.memory_ids} redacted={event.redacted}"
            )
            if event.failures:
                for failure in event.failures:
                    print(f"    * {failure}")
        if result.branch_ranks:
            top_branch = result.branch_ranks[0]
            print(
                "  "
                f"- branch_top={top_branch['branch_id']} "
                f"utility={top_branch['utility']:.4f}"
            )
        metrics = " ".join(
            f"{key}={value:.4f}" for key, value in sorted(result.metric_snapshot.items())
        )
        print(f"  - metrics: {metrics}")
        if result.failures:
            for failure in result.failures:
                print(f"    * {failure}")


def _write_json_output(results: list[VariantResult], output_path: Path) -> None:
    serializable = [
        {
            "scenario_id": item.scenario_id,
            "variant_id": item.variant_id,
            "passed": item.passed,
            "events": [
                {
                    "event_id": event.event_id,
                    "passed": event.passed,
                    "memory_ids": event.memory_ids,
                    "citation_ids": event.citation_ids,
                    "redacted": event.redacted,
                    "failures": event.failures,
                }
                for event in item.event_results
            ],
            "metric_snapshot": item.metric_snapshot,
            "branch_ranks": item.branch_ranks,
            "failures": item.failures,
        }
        for item in results
    ]
    output_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Attack on Memory scenario specs")
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Optional scenario JSON files. If omitted, all files under --scenarios-dir are used.",
    )
    parser.add_argument(
        "--scenarios-dir",
        default=str(Path(__file__).resolve().parent / "scenarios"),
        help="Directory that stores scenario JSON specs.",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional path to write run results as JSON.",
    )
    args = parser.parse_args(argv)

    scenario_files = _collect_scenario_files(args)
    if not scenario_files:
        print("No scenario files found.")
        return 1

    all_results: list[VariantResult] = []
    for scenario_path in scenario_files:
        spec = json.loads(scenario_path.read_text(encoding="utf-8"))
        ensure_valid_scenario_spec(spec)
        all_results.extend(run_scenario(spec))

    _print_results(all_results)

    if args.json_output:
        _write_json_output(all_results, Path(args.json_output).resolve())

    passed = sum(1 for result in all_results if result.passed)
    total = len(all_results)
    print(f"\nSummary: {passed}/{total} variants passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
