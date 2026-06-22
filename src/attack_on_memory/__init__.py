"""Attack on Memory: docs-first modular memory framework."""

from attack_on_memory.application.branch_world_model import (
    BranchEvaluation,
    BranchRank,
    BranchWorldModelService,
)
from attack_on_memory.application.conflict_resolution import ConflictMode, ConflictResolver
from attack_on_memory.application.lifecycle import MemoryLifecycleService
from attack_on_memory.application.services import CaptureService, RetrievalService
from attack_on_memory.application.vector_adapter import (
    NoopVectorIndex,
    TextEmbedder,
    VectorIndex,
    VectorMatch,
)
from attack_on_memory.domain.models import (
    Branch,
    BranchStatus,
    ConflictDecision,
    ConflictOutcome,
    EdgeType,
    Evidence,
    MemoryAtom,
    MemoryCitation,
    MemoryEdge,
    MemoryLifecycleRecord,
    MemoryLifecycleState,
    MemoryScope,
    ProjectedMemory,
    RetrievalQuery,
    RetrievedMemory,
    Sensitivity,
    TaskIntent,
    utc_now,
)
from attack_on_memory.evals.metrics import EvalTracker
from attack_on_memory.evals.north_star import NorthStarSnapshot, build_north_star_snapshot
from attack_on_memory.governance.audit import (
    GovernanceAuditSink,
    InMemoryGovernanceAuditSink,
)
from attack_on_memory.governance.analysis import (
    PolicyChangeReport,
    PolicyDecisionChange,
    PolicyDecisionSample,
    PolicyLintFinding,
    assert_no_permission_expansion,
    compare_policy_change,
    lint_policy,
    lint_policy_set,
)
from attack_on_memory.governance.policies import (
    DisclosurePolicy,
    GovernanceDecision,
    GovernanceEvaluation,
    MemoryGovernor,
)
from attack_on_memory.governance.signed_audit import (
    AuditSigner,
    AuditVerifier,
    Ed25519AuditSigner,
    Ed25519AuditVerifier,
    HMACSHA256AuditSigner,
    create_signed_audit_bundle,
    verify_signed_audit_bundle,
)
from attack_on_memory.infrastructure.in_memory import InMemoryStore
from attack_on_memory.infrastructure.hashing_embedder import HashingTextEmbedder
from attack_on_memory.infrastructure.sqlite_store import SQLiteStore
from attack_on_memory.infrastructure.store import MemoryStore, TransactionalMemoryStore
from attack_on_memory.runtime.context import ContextAssembler, ContextPacket
from attack_on_memory.runtime.openclaw_adapter import OpenClawMemoryAdapter, OpenClawTaskEvent
from attack_on_memory.scenarios.replay_converter import (
    build_scenario_from_replay,
    load_memory_catalog,
    load_replay_records,
)
from attack_on_memory.scenarios.spec_validation import (
    ensure_valid_scenario_spec,
    validate_scenario_spec,
)

__all__ = [
    "Branch",
    "AuditSigner",
    "AuditVerifier",
    "BranchEvaluation",
    "BranchRank",
    "BranchStatus",
    "BranchWorldModelService",
    "CaptureService",
    "ConflictDecision",
    "ConflictMode",
    "ConflictOutcome",
    "ConflictResolver",
    "ContextAssembler",
    "ContextPacket",
    "DisclosurePolicy",
    "EdgeType",
    "Ed25519AuditSigner",
    "Ed25519AuditVerifier",
    "EvalTracker",
    "Evidence",
    "GovernanceAuditSink",
    "GovernanceDecision",
    "GovernanceEvaluation",
    "InMemoryStore",
    "InMemoryGovernanceAuditSink",
    "HashingTextEmbedder",
    "HMACSHA256AuditSigner",
    "MemoryAtom",
    "MemoryCitation",
    "MemoryEdge",
    "MemoryGovernor",
    "MemoryLifecycleRecord",
    "MemoryLifecycleService",
    "MemoryLifecycleState",
    "MemoryScope",
    "MemoryStore",
    "NorthStarSnapshot",
    "OpenClawMemoryAdapter",
    "OpenClawTaskEvent",
    "PolicyChangeReport",
    "PolicyDecisionChange",
    "PolicyDecisionSample",
    "PolicyLintFinding",
    "ProjectedMemory",
    "build_scenario_from_replay",
    "assert_no_permission_expansion",
    "compare_policy_change",
    "create_signed_audit_bundle",
    "ensure_valid_scenario_spec",
    "load_memory_catalog",
    "load_replay_records",
    "lint_policy",
    "lint_policy_set",
    "RetrievalQuery",
    "RetrievalService",
    "RetrievedMemory",
    "Sensitivity",
    "SQLiteStore",
    "TaskIntent",
    "TextEmbedder",
    "TransactionalMemoryStore",
    "validate_scenario_spec",
    "verify_signed_audit_bundle",
    "utc_now",
    "VectorIndex",
    "VectorMatch",
    "NoopVectorIndex",
    "build_north_star_snapshot",
]
