# Launch Copy Pack (CN + EN)

## 1) GitHub Release 文案（中文）

**标题**
`v0.1.0 — 从“记忆比喻”到“可治理的多 Agent 记忆协议”`

**正文**
Attack on Memory v0.1.0 发布。

这不是另一个 RAG 包装器，而是一套面向多 Agent 协作的记忆协议层：
- 可寻址（Addressable）
- 可引用（Referable）
- 可继承（Inheritable）
- 可治理（Selective Disclosure + Policy）
- 可审计（Citations + Metrics）

### 这版包含
- 领域模型：MemoryAtom / MemoryEdge / Branch / TaskIntent
- 检索：时间窗检索 + 图邻居增强
- 治理：按角色与敏感度做选择性披露
- 运行时：OpenClaw Adapter（上下文注入 + 结果回写）
- 实验：Scenario Spec + Validator + Replay Converter
- 工程化：CI、Scorecard、Dependabot、Contributing/Security 基线

### 快速开始
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 examples/validate_scenarios.py
PYTHONPATH=src python3 examples/simulation_runner.py
```

### 下一步
- v0.2：向量索引 + 图数据库适配
- v0.2：基于真实回放的 benchmark 报告
- v0.2：更强的 anti-poisoning 治理策略

---

## 2) GitHub Release 文案（英文）

**Title**
`v0.1.0 — From memory metaphor to a governable multi-agent memory protocol`

**Body**
Attack on Memory v0.1.0 is live.

This is not another RAG wrapper. It is a memory protocol layer for multi-agent systems:
- Addressable memory units
- Referable evidence chains
- Inheritable operational experience
- Governed selective disclosure
- Auditable citations and metrics

### What’s included
- Domain model: `MemoryAtom`, `MemoryEdge`, `Branch`, `TaskIntent`
- Retrieval: time-window filtering + graph-neighbor boosting
- Governance: role/sensitivity-based projection
- Runtime: OpenClaw adapter (context injection + feedback writeback)
- Evaluation: scenario spec, validator, and replay converter
- OSS baseline: CI, Scorecard, Dependabot, Contributing/Security docs

### Quickstart
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 examples/validate_scenarios.py
PYTHONPATH=src python3 examples/simulation_runner.py
```

### Next
- v0.2: vector index + graph DB adapters
- v0.2: replay-driven benchmark publication
- v0.2: stronger anti-poisoning governance
