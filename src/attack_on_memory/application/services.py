"""Application services: capture and retrieval."""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from attack_on_memory.application.vector_adapter import NoopVectorIndex, VectorIndex
from attack_on_memory.domain.models import (
    EdgeType,
    MemoryAtom,
    MemoryLifecycleState,
    RetrievedMemory,
    RetrievalQuery,
)
from attack_on_memory.infrastructure.store import MemoryStore

TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+")


class CaptureService:
    """Service for persisting memory atoms."""

    def __init__(self, store: MemoryStore) -> None:
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
        store: MemoryStore,
        graph_bonus: float = 0.15,
        vector_index: VectorIndex | None = None,
        vector_bonus: float = 0.20,
        branch_bonus: float = 0.08,
        contradiction_penalty: float = 0.12,
        inherit_branch_memories: bool = True,
    ) -> None:
        self._store = store
        self._graph_bonus = graph_bonus
        self._vector_index = vector_index or NoopVectorIndex()
        self._vector_bonus = vector_bonus
        self._branch_bonus = branch_bonus
        self._contradiction_penalty = contradiction_penalty
        self._inherit_branch_memories = inherit_branch_memories

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedMemory]:
        intent = query.intent
        branch_lineage = (
            self._store.resolve_branch_lineage(intent.branch_id)
            if self._inherit_branch_memories
            else (intent.branch_id,)
        )
        candidates = [
            atom
            for atom in self._dedupe_branch_candidates(
                self._store.list_atoms(
                    branch_id=intent.branch_id,
                    include_inherited=self._inherit_branch_memories,
                ),
                branch_lineage,
            )
            if atom.scope.matches(domain=intent.domain, task=intent.task)
            and atom.is_active(intent.as_of)
            and self._is_lifecycle_active(atom.id)
            and self._in_lookback(atom, query)
        ]

        scored: list[RetrievedMemory] = []
        for atom in candidates:
            score, reason = self._score_atom(atom, query, branch_lineage=branch_lineage)
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

        scored = self._apply_contradiction_penalty(scored)

        ranked = sorted(scored, key=lambda item: item.score, reverse=True)
        return ranked[: query.top_k]

    def _is_lifecycle_active(self, atom_id: str) -> bool:
        lifecycle = self._store.get_lifecycle(atom_id)
        return lifecycle is None or lifecycle.state is MemoryLifecycleState.ACTIVE

    @staticmethod
    def _in_lookback(atom: MemoryAtom, query: RetrievalQuery) -> bool:
        if query.lookback is None:
            return True
        earliest = query.intent.as_of - query.lookback
        return atom.created_at >= earliest

    def _score_atom(
        self,
        atom: MemoryAtom,
        query: RetrievalQuery,
        *,
        branch_lineage: tuple[str, ...],
    ) -> tuple[float, str]:
        query_tokens = _tokenize(f"{query.intent.query} {query.intent.task}")
        atom_tokens = _tokenize(f"{atom.claim} {' '.join(atom.tags)}")

        overlap_score = _token_overlap(query_tokens, atom_tokens)
        confidence_score = atom.confidence
        recency_score = self._recency_score(atom, query)
        branch_score, branch_reason = self._branch_score(atom, query, branch_lineage)

        score = (
            0.50 * overlap_score
            + 0.28 * confidence_score
            + 0.14 * recency_score
            + self._branch_bonus * branch_score
        )
        reason = (
            f"token_overlap={overlap_score:.2f}; confidence={confidence_score:.2f}; "
            f"recency={recency_score:.2f}; {branch_reason}"
        )
        return score, reason

    def _branch_score(
        self,
        atom: MemoryAtom,
        query: RetrievalQuery,
        branch_lineage: tuple[str, ...],
    ) -> tuple[float, str]:
        if not branch_lineage:
            return 0.0, "branch_locality=0.00"

        index_by_branch = {branch_id: idx for idx, branch_id in enumerate(branch_lineage)}
        branch_index = index_by_branch.get(atom.branch_id, len(branch_lineage))
        if branch_index >= len(branch_lineage):
            return 0.0, f"branch={atom.branch_id}"

        if len(branch_lineage) == 1:
            locality = 1.0
        else:
            locality = 1.0 - (branch_index / (len(branch_lineage) - 1))

        if atom.branch_id == query.intent.branch_id:
            reason = f"branch_locality={locality:.2f}; branch={atom.branch_id}"
        else:
            reason = (
                f"branch_locality={locality:.2f}; inherited_from={atom.branch_id}"
            )
        return locality, reason

    def _apply_contradiction_penalty(
        self,
        scored: list[RetrievedMemory],
    ) -> list[RetrievedMemory]:
        score_by_id = {item.atom.id: item.score for item in scored}
        if not score_by_id:
            return scored

        contradiction_map: dict[str, list[str]] = {}
        for edge in self._store.list_edges(edge_type=EdgeType.CONTRADICTS):
            if edge.source_id not in score_by_id or edge.target_id not in score_by_id:
                continue
            contradiction_map.setdefault(edge.source_id, []).append(edge.target_id)
            contradiction_map.setdefault(edge.target_id, []).append(edge.source_id)

        adjusted: list[RetrievedMemory] = []
        for item in scored:
            opposing_ids = contradiction_map.get(item.atom.id, [])
            if not opposing_ids:
                adjusted.append(item)
                continue

            strongest_opponent = max(score_by_id[atom_id] for atom_id in opposing_ids)
            adjusted.append(
                RetrievedMemory(
                    atom=item.atom,
                    score=max(0.0, item.score - self._contradiction_penalty),
                    reason=(
                        f"{item.reason}; contradiction_risk={strongest_opponent:.2f}"
                        f"(-{self._contradiction_penalty:.2f})"
                    ),
                    conflicting_ids=tuple(sorted(opposing_ids)),
                )
            )
        return adjusted

    @staticmethod
    def _dedupe_branch_candidates(
        atoms: list[MemoryAtom],
        branch_lineage: tuple[str, ...],
    ) -> list[MemoryAtom]:
        lineage_index = {
            branch_id: idx for idx, branch_id in enumerate(branch_lineage)
        }
        ordered_atoms = sorted(
            atoms,
            key=lambda atom: (
                lineage_index.get(atom.branch_id, len(branch_lineage)),
                -atom.created_at.timestamp(),
                atom.id,
            ),
        )

        selected: list[MemoryAtom] = []
        seen_keys: set[str] = set()
        blocked_refs: set[str] = set()
        for atom in ordered_atoms:
            if atom.id in blocked_refs or atom.memory_key in blocked_refs:
                continue
            if atom.memory_key in seen_keys:
                continue
            selected.append(atom)
            seen_keys.add(atom.memory_key)
            blocked_refs.update(atom.supersedes)

        return selected

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
