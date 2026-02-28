# FAQ / 常见问题

## English

### 1) Is this just another RAG wrapper?
No. Attack on Memory focuses on **memory governance for multi-agent systems**:
- Addressable memory units
- Evidence-linked retrieval
- Role/sensitivity-based selective disclosure
- Branch world model for explicit alternatives

### 2) What is a Memory Atom?
A minimal verifiable memory unit:
`claim + evidence + source + confidence + scope + time + ttl + branch_id`.

### 3) How do you reduce stale memory risk?
By combining:
- TTL expiry
- lookback time-window retrieval
- branch-aware filtering

### 4) How do you prevent over-disclosure?
Through governance policies that project memory by role and sensitivity (deny-by-default for restricted roles).

### 5) How do you audit decisions?
Runtime packets include citations (`atom_id`, score, reason) so decisions can be traced back to evidence.

### 6) How do you evaluate quality?
Built-in metrics include:
`hit_rate`, `task_success_rate`, `repeat_error_rate`, `conflict_rate`, `contamination_rate`, latency, token cost.

### 7) Can this integrate with OpenClaw?
Yes. v0.1 includes an adapter for context injection + outcome writeback.

### 8) Is there a benchmark?
Use scenario simulation and replay conversion as baseline. A formal replay-driven benchmark report template is in `docs/BENCHMARK_REPORT_TEMPLATE.md`.

### 9) Is this production-ready?
v0.1 is a solid foundation (tests, scenarios, governance, CI), but backends are in-memory and retrieval is rule-based.

### 10) Where can I see concrete failure-mode examples?
- selective disclosure manipulation: `examples/scenarios/case_01_selective_disclosure_manipulation.json`
- inheritance and role handoff: `examples/scenarios/case_02_scout_inheritance.json`
- emergency privilege escalation controls: `examples/scenarios/case_03_rumbling_emergency_privilege.json`

### 11) How do I validate those scenarios?
```bash
PYTHONPATH=src python3 examples/validate_scenarios.py
PYTHONPATH=src python3 examples/simulation_runner.py
```

### 12) What is the operational recommendation for teams?
Start with scenario-driven governance checks before adding complex vector/graph backends.

### 13) What’s next?
v0.2 priorities:
- vector index adapter
- graph DB adapter
- stronger anti-poisoning governance

---

## 中文

### 1）这只是另一个 RAG 封装吗？
不是。Attack on Memory 关注的是**多 Agent 记忆治理**，核心包括：
- 可寻址记忆单元
- 证据链检索
- 基于角色/敏感度的选择性披露
- 显式分支世界模型

### 2）什么是 Memory Atom？
最小可验证记忆单元：
`claim + evidence + source + confidence + scope + time + ttl + branch_id`。

### 3）如何降低过期记忆风险？
通过以下组合机制：
- TTL 过期
- lookback 时间窗检索
- 分支感知过滤

### 4）如何防止过度披露？
通过治理策略按角色和敏感度投影记忆；对受限角色采用默认拒绝（deny-by-default）。

### 5）如何审计决策？
运行时数据包会包含引用信息（`atom_id`、score、reason），可追溯到具体证据。

### 6）如何评估质量？
内置指标包括：
`hit_rate`、`task_success_rate`、`repeat_error_rate`、`conflict_rate`、`contamination_rate`、延迟、token 成本。

### 7）能与 OpenClaw 集成吗？
可以。v0.1 已提供上下文注入与结果回写适配器。

### 8）有 benchmark 吗？
当前可用 scenario 仿真与 replay 转换作为基线。正式 replay 驱动报告模板在 `docs/BENCHMARK_REPORT_TEMPLATE.md`。

### 9）现在可用于生产吗？
v0.1 已具备扎实基础（测试、场景、治理、CI），但后端仍以内存实现、检索以规则为主。

### 10）哪里可以看具体失败模式案例？
- 选择性披露操控：`examples/scenarios/case_01_selective_disclosure_manipulation.json`
- 继承与角色交接：`examples/scenarios/case_02_scout_inheritance.json`
- 紧急权限升级控制：`examples/scenarios/case_03_rumbling_emergency_privilege.json`

### 11）如何验证这些场景？
```bash
PYTHONPATH=src python3 examples/validate_scenarios.py
PYTHONPATH=src python3 examples/simulation_runner.py
```

### 12）团队落地建议是什么？
先做 scenario 驱动治理校验，再逐步接入复杂向量/图后端。

### 13）下一步计划？
v0.2 优先级：
- 向量索引适配器
- 图数据库适配器
- 更强抗污染治理
