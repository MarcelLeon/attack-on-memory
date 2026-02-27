"""Convert OpenClaw replay logs into executable scenario specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from attack_on_memory.scenarios.spec_validation import ensure_valid_scenario_spec


def load_replay_records(path: str | Path) -> list[dict[str, Any]]:
    """Load replay records from JSON array, JSON object with events, or JSONL."""
    resolved = Path(path)
    content = resolved.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Replay input is empty: {resolved}")

    parsed: Any | None = None
    if content[0] in "[{":
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None

    if isinstance(parsed, list):
        return [_require_object(record, "record") for record in parsed]

    if isinstance(parsed, dict):
        events = parsed.get("events")
        if isinstance(events, list):
            return [_require_object(record, "record") for record in events]
        # Allow a single record object as replay input.
        return [parsed]

    # JSONL input fallback
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        record = json.loads(stripped)
        if not isinstance(record, dict):
            raise ValueError(f"Line {line_no} is not a JSON object")
        records.append(record)

    if not records:
        raise ValueError(f"No records parsed from replay file: {resolved}")
    return records


def load_memory_catalog(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load optional memory catalog used to fill real memory details."""
    resolved = Path(path)
    parsed = json.loads(resolved.read_text(encoding="utf-8"))

    if isinstance(parsed, dict):
        if "memories" in parsed and isinstance(parsed["memories"], list):
            memories = parsed["memories"]
        else:
            memories = []
            for key, value in parsed.items():
                if not isinstance(value, dict):
                    raise ValueError("Memory catalog dict values must be objects")
                value = {"id": key, **value}
                memories.append(value)
    elif isinstance(parsed, list):
        memories = parsed
    else:
        raise ValueError("Memory catalog must be a JSON object or array")

    catalog: dict[str, dict[str, Any]] = {}
    for entry in memories:
        memory = _require_object(entry, "memory catalog entry")
        memory_id = memory.get("id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise ValueError("Each memory catalog entry must include non-empty 'id'")
        catalog[memory_id] = memory
    return catalog


def build_scenario_from_replay(
    records: list[dict[str, Any]],
    *,
    scenario_id: str,
    title: str,
    description: str,
    variant_id: str = "replay_import",
    memory_catalog: dict[str, dict[str, Any]] | None = None,
    assert_from_context: bool = False,
) -> dict[str, Any]:
    """Convert replay records into a single-variant scenario spec."""
    if not records:
        raise ValueError("Replay records cannot be empty")

    if not scenario_id.strip() or not variant_id.strip():
        raise ValueError("scenario_id and variant_id must be non-empty")

    normalized_events = [_normalize_record(record, index=i) for i, record in enumerate(records)]
    roles = sorted({event["role"] for event in normalized_events})

    policies = [_build_policy_for_role(role, normalized_events) for role in roles]

    catalog = memory_catalog or {}
    referenced_memory_ids = _collect_memory_ids(normalized_events)
    default_domain = normalized_events[0]["domain"]
    default_task = normalized_events[0]["task"]
    memories = [
        _build_memory_spec(memory_id, catalog.get(memory_id), default_domain, default_task)
        for memory_id in sorted(referenced_memory_ids)
    ]

    events = [
        _build_event_spec(event, assert_from_context=assert_from_context)
        for event in normalized_events
    ]

    scenario = {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "title": title,
        "description": description,
        "variants": [
            {
                "variant_id": variant_id,
                "description": "Imported from OpenClaw replay logs.",
                "policies": policies,
                "memories": memories,
                "events": events,
                "metric_assertions": [],
            }
        ],
    }

    ensure_valid_scenario_spec(scenario)
    return scenario


def _normalize_record(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    event_id = _first_str(record, "event_id", "task_id", "id") or f"event_{index + 1}"
    actor = _first_str(record, "actor", "agent") or "unknown_actor"
    role = _first_str(record, "role") or "executor"
    domain = _first_str(record, "domain") or "unknown-domain"
    task = _first_str(record, "task") or "unknown-task"
    objective = _first_str(record, "objective", "query", "prompt") or "replay objective"
    branch_id = _first_str(record, "branch_id") or "main"

    seed_memory_ids = _to_str_list(record.get("seed_memory_ids", []))
    context = record.get("context") if isinstance(record.get("context"), dict) else {}
    projected_ids = _to_str_list(context.get("projected_memory_ids", []))
    cited_ids = _to_str_list(context.get("citation_ids", []))

    outcome = record.get("outcome") if isinstance(record.get("outcome"), dict) else {}
    if not outcome:
        outcome = {
            "success": bool(record.get("success", True)),
            "latency_ms": float(record.get("latency_ms", 0.0) or 0.0),
            "token_cost": float(record.get("token_cost", 0.0) or 0.0),
            "error_signature": record.get("error_signature"),
            "conflict": bool(record.get("conflict", False)),
            "contamination": bool(record.get("contamination", False)),
        }

    return {
        "event_id": event_id,
        "actor": actor,
        "role": role,
        "domain": domain,
        "task": task,
        "objective": objective,
        "branch_id": branch_id,
        "seed_memory_ids": seed_memory_ids,
        "top_k": int(record.get("top_k", 5) or 5),
        "lookback_days": int(record.get("lookback_days", 30) or 30),
        "graph_hops": int(record.get("graph_hops", 1) or 1),
        "projected_memory_ids": projected_ids,
        "citation_ids": cited_ids,
        "outcome": {
            "success": bool(outcome.get("success", True)),
            "latency_ms": float(outcome.get("latency_ms", 0.0) or 0.0),
            "token_cost": float(outcome.get("token_cost", 0.0) or 0.0),
            "error_signature": outcome.get("error_signature"),
            "conflict": bool(outcome.get("conflict", False)),
            "contamination": bool(outcome.get("contamination", False)),
        },
    }


def _build_policy_for_role(role: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    role_events = [event for event in events if event["role"] == role]
    domains = sorted({event["domain"] for event in role_events})
    tasks = sorted({event["task"] for event in role_events})
    return {
        "role": role,
        "max_sensitivity": "internal",
        "allowed_domains": domains,
        "allowed_tasks": tasks,
        "min_confidence": 0.0,
    }


def _collect_memory_ids(events: list[dict[str, Any]]) -> set[str]:
    memory_ids: set[str] = set()
    for event in events:
        memory_ids.update(event["seed_memory_ids"])
        memory_ids.update(event["projected_memory_ids"])
        memory_ids.update(event["citation_ids"])
    return memory_ids


def _build_memory_spec(
    memory_id: str,
    catalog_entry: dict[str, Any] | None,
    default_domain: str,
    default_task: str,
) -> dict[str, Any]:
    if catalog_entry is None:
        return {
            "id": memory_id,
            "claim": f"Replay placeholder memory for {memory_id}. Replace with real claim.",
            "source_agent": "replay_importer",
            "confidence": 0.8,
            "scope": {
                "domain": default_domain,
                "task": default_task,
                "owner": "shared",
            },
            "age_days": 1,
            "ttl_days": 30,
            "branch_id": "main",
            "sensitivity": "internal",
            "tags": ["replay", "placeholder"],
            "evidence": [
                {
                    "ref": f"replay:{memory_id}",
                    "source": "openclaw-log",
                    "age_days": 1,
                }
            ],
        }

    memory = dict(catalog_entry)
    memory.setdefault("id", memory_id)
    memory.setdefault("claim", f"Catalog memory {memory_id}")
    memory.setdefault("source_agent", "replay_catalog")
    memory.setdefault("confidence", 0.8)
    memory.setdefault(
        "scope",
        {
            "domain": default_domain,
            "task": default_task,
            "owner": "shared",
        },
    )
    memory.setdefault("age_days", 1)
    memory.setdefault("ttl_days", 30)
    memory.setdefault("branch_id", "main")
    memory.setdefault("sensitivity", "internal")
    memory.setdefault("tags", ["replay", "catalog"])
    memory.setdefault(
        "evidence",
        [
            {
                "ref": f"catalog:{memory_id}",
                "source": "memory-catalog",
                "age_days": 1,
            }
        ],
    )
    return memory


def _build_event_spec(
    event: dict[str, Any],
    *,
    assert_from_context: bool,
) -> dict[str, Any]:
    expected: dict[str, Any] = {}
    if assert_from_context and event["projected_memory_ids"]:
        expected["must_include"] = sorted(set(event["projected_memory_ids"]))
        expected["min_memories"] = len(expected["must_include"])

    payload = {
        "event_id": event["event_id"],
        "actor": event["actor"],
        "role": event["role"],
        "domain": event["domain"],
        "task": event["task"],
        "objective": event["objective"],
        "branch_id": event["branch_id"],
        "seed_memory_ids": event["seed_memory_ids"],
        "top_k": event["top_k"],
        "lookback_days": event["lookback_days"],
        "graph_hops": event["graph_hops"],
        "outcome": event["outcome"],
    }
    if expected:
        payload["expected"] = expected
    return payload


def _to_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _first_str(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value
