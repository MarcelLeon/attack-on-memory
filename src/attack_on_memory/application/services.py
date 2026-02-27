"""Application services: capture and retrieval."""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from attack_on_memory.application.vector_adapter import NoopVectorIndex, VectorIndex
from attack_on_memory.domain.models import MemoryAtom, RetrievedMemory, RetrievalQuery
from attack_on_memory.infrastructure.in_memory import InMemoryStore

TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+")


class CaptureService:
    """Service for persisting memory atoms."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def capture(self, atom: MemoryAtom) -> MemoryAtom:
        self._store.upsert_atom(atom)
        return atom

    @staticmethod
    def make_atom_id(seed: str) -> str:
        digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"mem_{digest[:12]}"


class RetrievalService:
    """Rule-based retrieval with time-window and graph expansion support."""

    def __init__(
        self,
        store: InMemoryStore,
        graph_bonus: float = 0.15,
        vector_index: VectorIndex | None = None,
        vector_bonus: float = 0.20,
    ) -> None:
        self._store = store
        self._graph_bonus = graph_bonus
        self._vector_index = vector_index or NoopVectorIndex()
        self._vector_bonus = vector_bonus

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedMemory]:
        intent = query.intent
        candidates = [
            atom
            for atom in self._store.list_atoms(branch_id=intent.branch_id)
            if atom.scope.matches(domain=intent.domain, task=intent.task)
            and atom.is_active(intent.as_of)
            and self._in_lookback(atom, query)
        ]

        scored: list[RetrievedMemory] = []
        for atom in candidates:
            score, reason = self._score_atom(atom, query)
            scored.append(RetrievedMemory(atom=atom, score=score, reason=reason))

        if query.seed_ids and query.graph_hops > 0:
            neighbors = self._store.neighboring_atom_ids(
                query.seed_ids,
                max_hops=query.graph_hops,
            )
            boosted: list[RetrievedMemory] = []
            for item in scored:
                if item.atom.id in neighbors:
                    boosted.append(
                        RetrievedMemory(
                            atom=item.atom,
                            score=item.score + self._graph_bonus,
                            reason=f"{item.reason}; graph_neighbor(+{self._graph_bonus:.2f})",
                        )
                    )
                else:
                    boosted.append(item)
            scored = boosted

        vector_hits = {
            hit.atom_id: hit.score
            for hit in self._vector_index.search(
                query=query.intent.query,
                top_k=max(query.top_k, 1),
            )
        }
        if vector_hits:
            boosted: list[RetrievedMemory] = []
            for item in scored:
                if item.atom.id in vector_hits:
                    boosted.append(
                        RetrievedMemory(
                            atom=item.atom,
                            score=item.score + self._vector_bonus,
                            reason=(
                                f"{item.reason}; vector_match={vector_hits[item.atom.id]:.2f}"
                                f"(+{self._vector_bonus:.2f})"
                            ),
                        )
                    )
                else:
                    boosted.append(item)
            scored = boosted

        ranked = sorted(scored, key=lambda item: item.score, reverse=True)
        return ranked[: query.top_k]

    @staticmethod
    def _in_lookback(atom: MemoryAtom, query: RetrievalQuery) -> bool:
        if query.lookback is None:
            return True
        earliest = query.intent.as_of - query.lookback
        return atom.created_at >= earliest

    def _score_atom(self, atom: MemoryAtom, query: RetrievalQuery) -> tuple[float, str]:
        query_tokens = _tokenize(f"{query.intent.query} {query.intent.task}")
        atom_tokens = _tokenize(f"{atom.claim} {' '.join(atom.tags)}")

        overlap_score = _token_overlap(query_tokens, atom_tokens)
        confidence_score = atom.confidence
        recency_score = self._recency_score(atom, query)

        score = 0.55 * overlap_score + 0.30 * confidence_score + 0.15 * recency_score
        reason = (
            f"token_overlap={overlap_score:.2f}; confidence={confidence_score:.2f}; "
            f"recency={recency_score:.2f}"
        )
        return score, reason

    @staticmethod
    def _recency_score(atom: MemoryAtom, query: RetrievalQuery) -> float:
        if query.lookback is None:
            ttl_seconds = atom.ttl.total_seconds()
            if ttl_seconds <= 0:
                return 0.0
            freshness = (atom.expires_at - query.intent.as_of).total_seconds() / ttl_seconds
            return max(0.0, min(1.0, freshness))

        elapsed = query.intent.as_of - atom.created_at
        if elapsed <= timedelta(0):
            return 1.0
        remaining = query.lookback - elapsed
        ratio = remaining.total_seconds() / query.lookback.total_seconds()
        return max(0.0, min(1.0, ratio))


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def _token_overlap(lhs: set[str], rhs: set[str]) -> float:
    if not lhs or not rhs:
        return 0.0
    intersection = lhs & rhs
    return len(intersection) / len(lhs)
