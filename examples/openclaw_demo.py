"""Minimal OpenClaw interaction demo for Attack on Memory framework."""

from __future__ import annotations

from datetime import timedelta

from attack_on_memory import (
    BranchEvaluation,
    BranchWorldModelService,
    CaptureService,
    ContextAssembler,
    DisclosurePolicy,
    EdgeType,
    EvalTracker,
    Evidence,
    InMemoryStore,
    MemoryAtom,
    MemoryEdge,
    MemoryGovernor,
    MemoryScope,
    OpenClawMemoryAdapter,
    OpenClawTaskEvent,
    RetrievalService,
    Sensitivity,
    utc_now,
)


def _seed_data(store: InMemoryStore, capture: CaptureService) -> None:
    now = utc_now()

    atom1 = MemoryAtom(
        id="mem_rate_limit_v2",
        claim="高峰故障时先启用 v2 限流，再做扩容，恢复更快。",
        evidence=(Evidence(ref="incident#214", source="ops-log", captured_at=now),),
        source_agent="reviewer",
        confidence=0.90,
        scope=MemoryScope(domain="operations", task="incident-response", owner="shared"),
        created_at=now - timedelta(days=3),
        ttl=timedelta(days=30),
        branch_id="main",
        sensitivity=Sensitivity.INTERNAL,
        tags=("限流", "扩容", "故障"),
    )

    atom2 = MemoryAtom(
        id="mem_sensitive_customer",
        claim="客户 A 的原始合同字段不可出现在执行日志。",
        evidence=(Evidence(ref="compliance#88", source="policy", captured_at=now),),
        source_agent="compliance",
        confidence=0.95,
        scope=MemoryScope(domain="operations", task="incident-response", owner="shared"),
        created_at=now - timedelta(days=1),
        ttl=timedelta(days=120),
        branch_id="main",
        sensitivity=Sensitivity.RESTRICTED,
        tags=("合规", "隐私"),
    )

    atom3 = MemoryAtom(
        id="mem_outdated_strategy",
        claim="使用旧版 v1 限流策略可以解决当前服务故障。",
        evidence=(Evidence(ref="incident#031", source="ops-log", captured_at=now),),
        source_agent="legacy-bot",
        confidence=0.60,
        scope=MemoryScope(domain="operations", task="incident-response", owner="shared"),
        created_at=now - timedelta(days=200),
        ttl=timedelta(days=7),
        branch_id="main",
        sensitivity=Sensitivity.INTERNAL,
        tags=("限流", "过期"),
    )

    capture.capture(atom1)
    capture.capture(atom2)
    capture.capture(atom3)

    store.add_edge(
        MemoryEdge(
            source_id=atom1.id,
            target_id=atom2.id,
            edge_type=EdgeType.SUPPORTS,
        )
    )


def build_openclaw_adapter() -> tuple[OpenClawMemoryAdapter, BranchWorldModelService, InMemoryStore]:
    store = InMemoryStore()
    capture_service = CaptureService(store)
    retrieval_service = RetrievalService(store)

    governor = MemoryGovernor()
    governor.register_policy(
        DisclosurePolicy(
            role="planner",
            max_sensitivity=Sensitivity.RESTRICTED,
            allowed_domains=frozenset({"operations"}),
            allowed_tasks=frozenset({"incident-response"}),
            min_confidence=0.65,
        )
    )
    governor.register_policy(
        DisclosurePolicy(
            role="executor",
            max_sensitivity=Sensitivity.INTERNAL,
            allowed_domains=frozenset({"operations"}),
            allowed_tasks=frozenset({"incident-response"}),
            min_confidence=0.65,
        )
    )

    assembler = ContextAssembler(retrieval_service, governor)
    tracker = EvalTracker()
    adapter = OpenClawMemoryAdapter(
        context_assembler=assembler,
        capture_service=capture_service,
        tracker=tracker,
    )

    _seed_data(store, capture_service)

    branch_service = BranchWorldModelService(store)
    branch_service.create_branch(
        branch_id="plan_a",
        name="先限流后扩容",
        hypothesis="优先稳定系统，延后资源成本",
        parent_id="main",
    )
    branch_service.create_branch(
        branch_id="plan_b",
        name="先扩容后限流",
        hypothesis="先保证吞吐，再处理风险",
        parent_id="main",
    )
    return adapter, branch_service, store


def main() -> None:
    adapter, branch_service, _ = build_openclaw_adapter()

    planner_event = OpenClawTaskEvent(
        task_id="task-1001",
        actor="openclaw-planner-01",
        role="planner",
        domain="operations",
        task="incident-response",
        objective="当前 API 报错率飙升，给出应急处置方案",
    )
    planner_context = adapter.build_context(planner_event, top_k=5, lookback_days=60)

    print("=== Planner Context ===")
    for item in planner_context.memories:
        print(f"- [{item.atom_id}] {item.claim} (conf={item.confidence:.2f})")
    print("diagnostics:", planner_context.diagnostics)

    adapter.record_outcome(success=True, latency_ms=180.0, token_cost=2200.0)

    executor_event = OpenClawTaskEvent(
        task_id="task-1002",
        actor="openclaw-executor-02",
        role="executor",
        domain="operations",
        task="incident-response",
        objective="按方案执行并写入执行日志",
        seed_memory_ids=("mem_rate_limit_v2",),
    )
    executor_context = adapter.build_context(executor_event, top_k=5, lookback_days=60)

    print("\n=== Executor Context ===")
    for item in executor_context.memories:
        print(f"- [{item.atom_id}] {item.claim} (conf={item.confidence:.2f})")
    print("diagnostics:", executor_context.diagnostics)

    adapter.record_outcome(
        success=False,
        latency_ms=260.0,
        token_cost=2500.0,
        error_signature="missing-redaction",
        conflict=True,
    )

    ranks = branch_service.rank_branches(
        [
            BranchEvaluation(branch_id="plan_a", success_rate=0.84, risk_score=0.26, cost_score=0.30),
            BranchEvaluation(branch_id="plan_b", success_rate=0.78, risk_score=0.40, cost_score=0.55),
        ]
    )
    print("\n=== Branch Ranking ===")
    for rank in ranks:
        print(f"- {rank.branch_id}: utility={rank.utility:.3f}")

    print("\n=== Metrics Snapshot ===")
    for key, value in adapter.metrics_snapshot().items():
        print(f"{key}={value:.4f}")


if __name__ == "__main__":
    main()
