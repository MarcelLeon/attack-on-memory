"""Paired replay benchmark for recent-context and governed-memory systems."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from attack_on_memory.application.conflict_resolution import ConflictMode, ConflictResolver
from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.domain.models import (
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryEdge,
    MemoryScope,
    Sensitivity,
    TaskIntent,
)
from attack_on_memory.governance.policies import DisclosurePolicy, MemoryGovernor
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.runtime.context import ContextAssembler


METRIC_NAMES = (
    "context_acceptance_rate",
    "relevant_recall",
    "relevant_precision",
    "unsafe_inclusion_rate",
    "conflict_exposure_rate",
    "avg_context_size",
)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    selected_ids: tuple[str, ...]
    context_accepted: float
    relevant_recall: float
    relevant_precision: float
    unsafe_inclusion_rate: float
    conflict_exposure_rate: float
    context_size: float


def load_replay_benchmark(
    path: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Load and validate a privacy-safe labeled replay benchmark."""
    raw_dataset = path.read_bytes()
    dataset = json.loads(raw_dataset, object_pairs_hook=_reject_duplicate_json_keys)
    if not isinstance(dataset, dict):
        raise ValueError("benchmark must be a JSON object")
    metadata = dataset.get("metadata", {})
    if metadata.get("privacy") not in {"synthetic", "sanitized"}:
        raise ValueError("benchmark metadata.privacy must be synthetic or sanitized")
    if not dataset.get("cases"):
        raise ValueError("benchmark must contain at least one replay case")
    if not dataset.get("memories"):
        raise ValueError("benchmark must contain a memory catalog")
    memory_ids = [item.get("id") for item in dataset["memories"]]
    if any(not isinstance(item_id, str) or not item_id for item_id in memory_ids):
        raise ValueError("every benchmark memory must have a non-empty id")
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError("benchmark memory ids must be unique")
    known_ids = set(memory_ids)
    case_ids: set[str] = set()
    for case in dataset["cases"]:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("every replay case must have a non-empty case_id")
        if case_id in case_ids:
            raise ValueError(f"duplicate replay case_id: {case_id}")
        case_ids.add(case_id)
        if not case.get("relevant_memory_ids"):
            raise ValueError(f"{case_id} must label at least one relevant memory")
        if int(case.get("top_k", 5)) <= 0:
            raise ValueError(f"{case_id}.top_k must be > 0")
        referenced = set(case.get("recent_memory_ids", ()))
        referenced.update(case.get("relevant_memory_ids", ()))
        referenced.update(case.get("required_memory_ids", ()))
        referenced.update(case.get("forbidden_memory_ids", ()))
        unknown = referenced - known_ids
        if unknown:
            raise ValueError(f"{case_id} references unknown memories: {sorted(unknown)}")
    for edge in dataset.get("edges", []):
        unknown = {edge.get("source_id"), edge.get("target_id")} - known_ids
        if unknown:
            raise ValueError(f"benchmark edge references unknown memories: {sorted(unknown)}")
    manifest = _load_evidence_manifest(
        manifest_path or path.with_name(f"{path.stem}.manifest.json"),
        dataset_path=path,
        dataset=dataset,
        raw_dataset=raw_dataset,
    )
    dataset["_evidence_manifest"] = manifest
    return dataset


def replay_label_digest(dataset: Mapping[str, Any]) -> str:
    """Hash only evaluation labels so post-hoc relabeling is detectable."""
    labels = [
        {
            "case_id": case["case_id"],
            "relevant_memory_ids": case["relevant_memory_ids"],
            "required_memory_ids": case.get(
                "required_memory_ids", case["relevant_memory_ids"]
            ),
            "forbidden_memory_ids": case.get("forbidden_memory_ids", []),
        }
        for case in dataset["cases"]
    ]
    canonical = json.dumps(
        labels,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_replay_benchmark(
    dataset: dict[str, Any],
    *,
    bootstrap_samples: int = 5000,
    seed: int = 20260619,
) -> dict[str, Any]:
    """Run paired control/treatment evaluation and deterministic bootstrap CIs."""
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be > 0")

    store, conflict_pairs = _build_store(dataset)
    assembler = _build_assembler(dataset, store)
    control_results: list[CaseResult] = []
    treatment_results: list[CaseResult] = []

    for case in dataset["cases"]:
        top_k = int(case.get("top_k", 5))
        control_ids = tuple(case.get("recent_memory_ids", ()))[:top_k]
        packet = assembler.assemble(
            TaskIntent(
                request_id=case["case_id"],
                actor=case.get("actor", "benchmark-agent"),
                role=case["role"],
                domain=case["domain"],
                task=case["task"],
                query=case["query"],
                branch_id=case.get("branch_id", "main"),
                as_of=_parse_time(dataset["metadata"]["as_of"]),
            ),
            top_k=top_k,
            lookback_days=case.get("lookback_days", 30),
            graph_hops=int(case.get("graph_hops", 0)),
        )
        treatment_ids = tuple(item.atom_id for item in packet.memories)
        control_results.append(_score_case(case, control_ids, conflict_pairs))
        treatment_results.append(_score_case(case, treatment_ids, conflict_pairs))

    control_metrics = _aggregate(control_results)
    treatment_metrics = _aggregate(treatment_results)
    deltas = _paired_bootstrap(
        control_results,
        treatment_results,
        samples=bootstrap_samples,
        seed=seed,
    )
    return {
        "schema_version": 1,
        "dataset": dataset["metadata"],
        "evidence_manifest": dataset["_evidence_manifest"],
        "method": {
            "design": "paired replay evaluation",
            "control": "ungoverned recent-context top-k",
            "treatment": "Attack on Memory retrieval + governance + conflict resolution",
            "bootstrap_samples": bootstrap_samples,
            "bootstrap_seed": seed,
            "confidence_level": 0.95,
        },
        "sample_size": len(control_results),
        "control": control_metrics,
        "treatment": treatment_metrics,
        "deltas": deltas,
        "cases": {
            "control": [asdict(item) for item in control_results],
            "treatment": [asdict(item) for item in treatment_results],
        },
    }


def render_replay_report(result: dict[str, Any]) -> str:
    """Render benchmark JSON as a concise, claim-bounded Markdown report."""
    metadata = result["dataset"]
    lines = [
        "# Replay Benchmark v0.2",
        "",
        (
            f"> {metadata['privacy'].title()} fixture; this measures the checked-in "
            "replay suite, not production traffic or universal superiority."
        ),
        "",
        "## Dataset and method",
        "",
        f"- Dataset: `{metadata['name']}` ({result['sample_size']} paired replay cases)",
        f"- As-of: `{metadata['as_of']}`",
        f"- Evidence class: `{result['evidence_manifest']['evidence_class']}`",
        f"- Dataset SHA-256: `{result['evidence_manifest']['dataset_sha256']}`",
        f"- Frozen label-set SHA-256: `{result['evidence_manifest']['label_set_sha256']}`",
        f"- Control: {result['method']['control']}",
        f"- Treatment: {result['method']['treatment']}",
        (
            f"- Uncertainty: paired bootstrap, {result['method']['bootstrap_samples']} "
            f"samples, seed {result['method']['bootstrap_seed']}, 95% interval"
        ),
        "",
        "## Results",
        "",
        "| Metric | Control | Treatment | Delta | 95% CI |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "context_acceptance_rate": "Context acceptance rate ↑",
        "relevant_recall": "Relevant recall ↑",
        "relevant_precision": "Relevant precision ↑",
        "unsafe_inclusion_rate": "Unsafe inclusion rate ↓",
        "conflict_exposure_rate": "Conflict exposure rate ↓",
        "avg_context_size": "Average context size ↓",
    }
    for metric in METRIC_NAMES:
        delta = result["deltas"][metric]
        lines.append(
            f"| {labels[metric]} | {result['control'][metric]:.3f} | "
            f"{result['treatment'][metric]:.3f} | {delta['estimate']:+.3f} | "
            f"[{delta['ci_low']:+.3f}, {delta['ci_high']:+.3f}] |"
        )
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```bash",
            "make replay-benchmark",
            "```",
            "",
            "The JSON artifact includes per-case selected memory IDs for auditability.",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_evidence_manifest(
    path: Path,
    *,
    dataset_path: Path,
    dataset: Mapping[str, Any],
    raw_dataset: bytes,
) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"benchmark evidence manifest is missing: {path.name}")
    manifest = json.loads(
        path.read_bytes(),
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    expected_fields = {
        "schema_version",
        "dataset_file",
        "dataset_sha256",
        "label_set_sha256",
        "evidence_class",
        "registered_at",
        "labeling",
        "privacy_review",
        "source",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_fields:
        raise ValueError("benchmark evidence manifest fields are invalid")
    if manifest["schema_version"] != 1 or isinstance(manifest["schema_version"], bool):
        raise ValueError("unsupported benchmark evidence manifest schema")
    if manifest["dataset_file"] != dataset_path.name:
        raise ValueError("benchmark evidence manifest dataset_file does not match")
    expected_dataset_digest = hashlib.sha256(raw_dataset).hexdigest()
    if manifest["dataset_sha256"] != expected_dataset_digest:
        raise ValueError("benchmark dataset SHA-256 does not match evidence manifest")
    expected_label_digest = replay_label_digest(dataset)
    if manifest["label_set_sha256"] != expected_label_digest:
        raise ValueError("benchmark label-set SHA-256 does not match evidence manifest")
    privacy = dataset["metadata"]["privacy"]
    expected_class = {
        "synthetic": "synthetic-development",
        "sanitized": "sanitized-execution-derived",
    }[privacy]
    if manifest["evidence_class"] != expected_class:
        raise ValueError("benchmark evidence class does not match dataset privacy")
    registered_at = _aware_time(manifest["registered_at"], "registered_at")
    labeling = manifest["labeling"]
    if not isinstance(labeling, dict) or set(labeling) != {
        "protocol",
        "reviewer",
        "locked_at",
        "independent_of_system_output",
    }:
        raise ValueError("benchmark labeling manifest is invalid")
    if labeling["independent_of_system_output"] is not True:
        raise ValueError("benchmark labels must be independent of system output")
    if any(
        not isinstance(labeling[field], str) or not labeling[field].strip()
        for field in ("protocol", "reviewer")
    ):
        raise ValueError("benchmark labeling protocol and reviewer are required")
    locked_at = _aware_time(labeling["locked_at"], "labeling.locked_at")
    if locked_at > registered_at:
        raise ValueError("benchmark labels must be locked before manifest registration")
    privacy_review = manifest["privacy_review"]
    if not isinstance(privacy_review, dict) or set(privacy_review) != {
        "status",
        "reviewer",
        "reviewed_at",
    }:
        raise ValueError("benchmark privacy review manifest is invalid")
    allowed_privacy_status = (
        {"not-required-synthetic", "approved"} if privacy == "synthetic" else {"approved"}
    )
    if privacy_review["status"] not in allowed_privacy_status:
        raise ValueError("sanitized execution replay requires approved privacy review")
    if not isinstance(privacy_review["reviewer"], str) or not privacy_review[
        "reviewer"
    ].strip():
        raise ValueError("benchmark privacy reviewer is required")
    _aware_time(privacy_review["reviewed_at"], "privacy_review.reviewed_at")
    source = manifest["source"]
    if not isinstance(source, dict) or set(source) != {
        "kind",
        "systems",
        "window_start",
        "window_end",
    }:
        raise ValueError("benchmark source manifest is invalid")
    expected_source_kind = "fixture" if privacy == "synthetic" else "production-execution"
    if source["kind"] != expected_source_kind:
        raise ValueError("benchmark source kind does not match evidence class")
    if (
        not isinstance(source["systems"], list)
        or not source["systems"]
        or any(not isinstance(item, str) or not item.strip() for item in source["systems"])
    ):
        raise ValueError("benchmark source systems are required")
    if privacy == "sanitized":
        start = _aware_time(source["window_start"], "source.window_start")
        end = _aware_time(source["window_end"], "source.window_end")
        if start > end:
            raise ValueError("benchmark source window is invalid")
    elif source["window_start"] is not None or source["window_end"] is not None:
        raise ValueError("synthetic replay source window must be null")
    return manifest


def _aware_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"benchmark evidence {field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"benchmark evidence {field} must be timezone-aware")
    return parsed


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"benchmark contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _build_store(dataset: dict[str, Any]) -> tuple[InMemoryStore, set[frozenset[str]]]:
    as_of = _parse_time(dataset["metadata"]["as_of"])
    store = InMemoryStore()
    capture = CaptureService(store)
    for raw in dataset["memories"]:
        evidence = tuple(
            Evidence(
                ref=item["ref"],
                source=item["source"],
                captured_at=as_of - timedelta(days=float(item.get("age_days", 0))),
            )
            for item in raw["evidence"]
        )
        capture.capture(
            MemoryAtom(
                id=raw["id"],
                claim=raw["claim"],
                evidence=evidence,
                source_agent=raw["source_agent"],
                confidence=float(raw["confidence"]),
                scope=MemoryScope(**raw["scope"]),
                created_at=as_of - timedelta(days=float(raw.get("age_days", 0))),
                ttl=timedelta(days=float(raw.get("ttl_days", 30))),
                branch_id=raw.get("branch_id", "main"),
                sensitivity=Sensitivity(raw.get("sensitivity", "internal")),
                tags=tuple(raw.get("tags", ())),
                metadata=raw.get("metadata", {}),
            )
        )

    conflict_pairs: set[frozenset[str]] = set()
    for edge in dataset.get("edges", []):
        edge_type = EdgeType(edge["edge_type"])
        store.add_edge(
            MemoryEdge(
                source_id=edge["source_id"],
                target_id=edge["target_id"],
                edge_type=edge_type,
            )
        )
        if edge_type is EdgeType.CONTRADICTS:
            conflict_pairs.add(frozenset({edge["source_id"], edge["target_id"]}))
    return store, conflict_pairs


def _build_assembler(dataset: dict[str, Any], store: InMemoryStore) -> ContextAssembler:
    governor = MemoryGovernor()
    for raw in dataset["policies"]:
        governor.register_policy(
            DisclosurePolicy(
                role=raw["role"],
                max_sensitivity=Sensitivity(raw.get("max_sensitivity", "internal")),
                allowed_domains=frozenset(raw.get("allowed_domains", ())),
                allowed_tasks=frozenset(raw.get("allowed_tasks", ())),
                min_confidence=float(raw.get("min_confidence", 0.0)),
            )
        )
    return ContextAssembler(
        RetrievalService(store),
        governor,
        ConflictResolver(mode=ConflictMode.PREFER_STRONGER),
    )


def _score_case(
    case: dict[str, Any],
    selected_ids: tuple[str, ...],
    conflict_pairs: set[frozenset[str]],
) -> CaseResult:
    selected = set(selected_ids)
    relevant = set(case["relevant_memory_ids"])
    required = set(case.get("required_memory_ids", case["relevant_memory_ids"]))
    forbidden = set(case.get("forbidden_memory_ids", ()))
    conflict_exposed = any(pair <= selected for pair in conflict_pairs)
    relevant_recall = len(selected & relevant) / len(relevant) if relevant else 1.0
    relevant_precision = len(selected & relevant) / len(selected) if selected else 0.0
    unsafe_rate = len(selected & forbidden) / len(selected) if selected else 0.0
    accepted = required <= selected and not (selected & forbidden) and not conflict_exposed
    return CaseResult(
        case_id=case["case_id"],
        selected_ids=selected_ids,
        context_accepted=float(accepted),
        relevant_recall=relevant_recall,
        relevant_precision=relevant_precision,
        unsafe_inclusion_rate=unsafe_rate,
        conflict_exposure_rate=float(conflict_exposed),
        context_size=float(len(selected_ids)),
    )


def _aggregate(results: Iterable[CaseResult]) -> dict[str, float]:
    rows = list(results)
    return {
        "context_acceptance_rate": _mean(item.context_accepted for item in rows),
        "relevant_recall": _mean(item.relevant_recall for item in rows),
        "relevant_precision": _mean(item.relevant_precision for item in rows),
        "unsafe_inclusion_rate": _mean(item.unsafe_inclusion_rate for item in rows),
        "conflict_exposure_rate": _mean(item.conflict_exposure_rate for item in rows),
        "avg_context_size": _mean(item.context_size for item in rows),
    }


def _paired_bootstrap(
    control: list[CaseResult],
    treatment: list[CaseResult],
    *,
    samples: int,
    seed: int,
) -> dict[str, dict[str, float]]:
    rng = random.Random(seed)
    count = len(control)
    output: dict[str, dict[str, float]] = {}
    fields = {
        "context_acceptance_rate": "context_accepted",
        "relevant_recall": "relevant_recall",
        "relevant_precision": "relevant_precision",
        "unsafe_inclusion_rate": "unsafe_inclusion_rate",
        "conflict_exposure_rate": "conflict_exposure_rate",
        "avg_context_size": "context_size",
    }
    for metric, field in fields.items():
        paired = [
            getattr(treatment[index], field) - getattr(control[index], field)
            for index in range(count)
        ]
        estimates = sorted(
            _mean(paired[rng.randrange(count)] for _ in range(count))
            for _ in range(samples)
        )
        output[metric] = {
            "estimate": _mean(paired),
            "ci_low": _percentile(estimates, 0.025),
            "ci_high": _percentile(estimates, 0.975),
        }
    return output


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _percentile(values: list[float], quantile: float) -> float:
    index = (len(values) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
