"""Vector index adapter contracts (scaffold for v0.2 backends)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VectorMatch:
    """A vector retrieval hit for a memory atom id."""

    atom_id: str
    score: float


class VectorIndex(Protocol):
    """Pluggable vector index contract."""

    def search(self, *, query: str, top_k: int) -> list[VectorMatch]:
        """Return ranked vector matches for a query string."""


class NoopVectorIndex:
    """Default no-op index used when no vector backend is configured."""

    def search(self, *, query: str, top_k: int) -> list[VectorMatch]:  # noqa: ARG002
        return []
