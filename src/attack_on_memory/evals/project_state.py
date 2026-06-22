"""Machine-checkable project goal and delivery ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = frozenset({"done", "in_progress", "planned", "blocked"})


def load_project_state(path: Path) -> dict[str, Any]:
    """Load a project-state document from JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_project_state(state: dict[str, Any], repo_root: Path) -> list[str]:
    """Return validation failures for a project-state document."""
    failures: list[str] = []
    if not _text(state.get("goal")):
        failures.append("goal must be a non-empty string")

    north_star = state.get("north_star")
    if not isinstance(north_star, dict):
        failures.append("north_star must be an object")
    else:
        for field in ("metric", "definition", "evidence_command"):
            if not _text(north_star.get(field)):
                failures.append(f"north_star.{field} must be a non-empty string")

    deliverables = state.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        failures.append("deliverables must be a non-empty list")
        deliverables = []

    deliverable_ids: set[str] = set()
    for index, item in enumerate(deliverables):
        label = f"deliverables[{index}]"
        if not isinstance(item, dict):
            failures.append(f"{label} must be an object")
            continue
        item_id = item.get("id")
        if not _text(item_id):
            failures.append(f"{label}.id must be a non-empty string")
        elif item_id in deliverable_ids:
            failures.append(f"duplicate deliverable id: {item_id}")
        else:
            deliverable_ids.add(item_id)
        if not _text(item.get("title")):
            failures.append(f"{label}.title must be a non-empty string")
        status = item.get("status")
        if status not in ALLOWED_STATUSES:
            failures.append(f"{label}.status must be one of {sorted(ALLOWED_STATUSES)}")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            failures.append(f"{label}.evidence must be a list")
            evidence = []
        if status == "done" and not evidence:
            failures.append(f"{label} is done but has no evidence")
        for raw_path in evidence:
            if not _text(raw_path):
                failures.append(f"{label}.evidence contains an invalid path")
            elif not (repo_root / raw_path).exists():
                failures.append(f"{label}.evidence path does not exist: {raw_path}")

    milestone = state.get("current_milestone")
    if not isinstance(milestone, dict):
        failures.append("current_milestone must be an object")
    else:
        for field in ("id", "title", "outcome"):
            if not _text(milestone.get(field)):
                failures.append(f"current_milestone.{field} must be a non-empty string")
        milestone_ids = milestone.get("deliverable_ids", [])
        if not isinstance(milestone_ids, list) or not milestone_ids:
            failures.append("current_milestone.deliverable_ids must be non-empty")
        else:
            for item_id in milestone_ids:
                if item_id not in deliverable_ids:
                    failures.append(
                        f"current milestone references unknown deliverable: {item_id}"
                    )

    capabilities = state.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        failures.append("capabilities must be a non-empty list")
    else:
        for index, capability in enumerate(capabilities):
            label = f"capabilities[{index}]"
            if not isinstance(capability, dict):
                failures.append(f"{label} must be an object")
                continue
            if not _text(capability.get("name")):
                failures.append(f"{label}.name must be a non-empty string")
            if capability.get("status") not in ALLOWED_STATUSES:
                failures.append(f"{label}.status must be one of {sorted(ALLOWED_STATUSES)}")
            if not _text(capability.get("next_gate")):
                failures.append(f"{label}.next_gate must be a non-empty string")

    return failures


def render_project_status(state: dict[str, Any]) -> str:
    """Render the ledger into a compact status report for humans and agents."""
    deliverables = state["deliverables"]
    totals = {status: 0 for status in ALLOWED_STATUSES}
    for item in deliverables:
        totals[item["status"]] += 1

    milestone = state["current_milestone"]
    milestone_ids = set(milestone["deliverable_ids"])
    lines = [
        "Attack on Memory project status",
        "=" * 31,
        f"Goal: {state['goal']}",
        f"North star: {state['north_star']['metric']}",
        f"Target: {state['north_star']['target']}",
        f"Evidence: {state['north_star']['evidence_command']}",
        "",
        f"Current milestone: {milestone['id']} — {milestone['title']}",
        f"Outcome: {milestone['outcome']}",
        (
            "Delivery: "
            f"{totals['done']} done / {totals['in_progress']} in progress / "
            f"{totals['planned']} planned / {totals['blocked']} blocked"
        ),
        "",
        "Milestone deliverables",
    ]
    symbols = {"done": "✓", "in_progress": "→", "planned": "·", "blocked": "!"}
    for item in deliverables:
        if item["id"] in milestone_ids:
            lines.append(
                f"- {symbols[item['status']]} {item['id']} [{item['status']}] "
                f"{item['title']}"
            )

    lines.extend(["", "Capability frontier"])
    for capability in state["capabilities"]:
        lines.append(
            f"- {symbols[capability['status']]} {capability['name']}: "
            f"{capability['next_gate']}"
        )

    active = [
        item for item in deliverables if item["status"] in {"in_progress", "blocked"}
    ]
    if active:
        lines.extend(["", "Next actions"])
        for item in active:
            lines.append(f"- {item['id']}: {item['next_action']}")
    return "\n".join(lines)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
