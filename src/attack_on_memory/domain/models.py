"""Core domain models for the Attack on Memory framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class Sensitivity(str, Enum):
    """Data sensitivity levels for selective disclosure."""

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    SECRET = "secret"


SENSITIVITY_ORDER: dict[Sensitivity, int] = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.RESTRICTED: 2,
    Sensitivity.SECRET: 3,
}


class EdgeType(str, Enum):
    """Relationship types between memory atoms."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    INHERITED_FROM = "inherited_from"
    CAUSED_BY = "caused_by"


class BranchStatus(str, Enum):
    """Lifecycle status for world-model branches."""

    ACTIVE = "active"
    MERGED = "merged"
    REJECTED = "rejected"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Evidence:
    """Evidence reference attached to a memory atom."""

    ref: str
    source: str
    captured_at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise ValueError("Evidence.ref cannot be empty")
        if not self.source.strip():
            raise ValueError("Evidence.source cannot be empty")
        _validate_aware_datetime(self.captured_at, "Evidence.captured_at")


@dataclass(frozen=True)
class MemoryScope:
    """Scope boundaries for where a memory atom can be applied."""

    domain: str
    task: str
    owner: str = "shared"

    def matches(
        self,
        domain: str | None = None,
        task: str | None = None,
        owner: str | None = None,
    ) -> bool:
        if domain is not None and self.domain != domain:
            return False
        if task is not None and self.task != task:
            return False
        if owner is not None and self.owner != owner:
            return False
        return True


@dataclass(frozen=True)
class MemoryAtom:
    """Smallest verifiable memory unit."""

    id: str
    claim: str
    evidence: tuple[Evidence, ...]
    source_agent: str
    confidence: float
    scope: MemoryScope
    created_at: datetime
    ttl: timedelta
    branch_id: str = "main"
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("MemoryAtom.id cannot be empty")
        if not self.claim.strip():
            raise ValueError("MemoryAtom.claim cannot be empty")
        if not self.source_agent.strip():
            raise ValueError("MemoryAtom.source_agent cannot be empty")
        if not self.evidence:
            raise ValueError("MemoryAtom.evidence cannot be empty")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("MemoryAtom.confidence must be between 0 and 1")
        if self.ttl <= timedelta(0):
            raise ValueError("MemoryAtom.ttl must be > 0")
        _validate_aware_datetime(self.created_at, "MemoryAtom.created_at")

    @property
    def expires_at(self) -> datetime:
        return self.created_at + self.ttl

    def is_active(self, at: datetime | None = None) -> bool:
        check_time = at or utc_now()
        _validate_aware_datetime(check_time, "at")
        return check_time < self.expires_at


@dataclass(frozen=True)
class MemoryEdge:
    """Directed relationship between memory atoms."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.target_id.strip():
            raise ValueError("MemoryEdge node ids cannot be empty")
        if self.weight <= 0:
            raise ValueError("MemoryEdge.weight must be > 0")


@dataclass(frozen=True)
class Branch:
    """Explicit hypothesis branch for branch-world modeling."""

    id: str
    name: str
    hypothesis: str
    created_at: datetime
    parent_id: str | None = None
    status: BranchStatus = BranchStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Branch.id cannot be empty")
        if not self.name.strip():
            raise ValueError("Branch.name cannot be empty")
        _validate_aware_datetime(self.created_at, "Branch.created_at")


@dataclass(frozen=True)
class TaskIntent:
    """Runtime query intent from an executing role."""

    request_id: str
    actor: str
    role: str
    domain: str
    task: str
    query: str
    branch_id: str = "main"
    as_of: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "actor",
            "role",
            "domain",
            "task",
            "query",
            "branch_id",
        ):
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(f"TaskIntent.{field_name} cannot be empty")
        _validate_aware_datetime(self.as_of, "TaskIntent.as_of")


@dataclass(frozen=True)
class RetrievalQuery:
    """Retrieval parameters for memory search."""

    intent: TaskIntent
    top_k: int = 5
    lookback: timedelta | None = timedelta(days=30)
    seed_ids: tuple[str, ...] = ()
    graph_hops: int = 1

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("RetrievalQuery.top_k must be > 0")
        if self.lookback is not None and self.lookback <= timedelta(0):
            raise ValueError("RetrievalQuery.lookback must be > 0 when provided")
        if self.graph_hops < 0:
            raise ValueError("RetrievalQuery.graph_hops cannot be negative")


@dataclass(frozen=True)
class RetrievedMemory:
    """Ranked retrieval result with scoring metadata."""

    atom: MemoryAtom
    score: float
    reason: str


@dataclass(frozen=True)
class ProjectedMemory:
    """Memory view returned after governance filtering."""

    atom_id: str
    claim: str
    confidence: float
    scope: MemoryScope
    branch_id: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryCitation:
    """Reference entry used for runtime auditability."""

    atom_id: str
    score: float
    reason: str
