# Agent Memory Framework v0.1（文档先行）

## 1. 目标与边界

### 1.1 目标
- 提供一个可验证、可治理、可演化的 Agent Memory 框架。
- 用模块化架构把 `Memory Atom`、`Selective Disclosure`、`BranchWorldModel` 落到工程实现。
- 以低耦合方式对接上层应用（本阶段以 OpenClaw 为目标受众）。

### 1.2 非目标
- 不追求“全量共享记忆”。
- 不提供不可审计的黑盒记忆注入。
- 不把向量相似度等同于真实性证明。

## 2. 设计原则

- 领域优先：先定义领域对象，再定义接口与存储。
- 模块化：领域、应用、治理、基础设施、运行时、评估分层。
- 可维护：接口稳定，依赖方向单向（上层依赖抽象，下层实现抽象）。
- 可演化：先用内存实现跑通流程，再平滑替换为数据库/图引擎。

## 3. 模块架构

| 层 | 职责 | 对应代码 |
|---|---|---|
| `domain` | 领域模型与不变量 | `src/attack_on_memory/domain/models.py` |
| `infrastructure` | 存储与图关系实现 | `src/attack_on_memory/infrastructure/in_memory.py` |
| `application` | 捕获、检索、分支推演服务 | `src/attack_on_memory/application/services.py`, `src/attack_on_memory/application/branch_world_model.py` |
| `governance` | 选择性披露、权限治理 | `src/attack_on_memory/governance/policies.py` |
| `runtime` | 上下文装配与应用对接（OpenClaw） | `src/attack_on_memory/runtime/context.py`, `src/attack_on_memory/runtime/openclaw_adapter.py` |
| `evals` | 质量指标与运行观测 | `src/attack_on_memory/evals/metrics.py` |
| `examples` | 最小可运行示例 | `examples/openclaw_demo.py` |

## 4. 领域模型（Domain Modeling）

### 4.1 MemoryAtom
最小可验证单元，关键字段：
- `id`: 稳定寻址。
- `claim`: 断言内容。
- `evidence`: 证据引用集合。
- `source_agent`: 产生者。
- `confidence`: 置信度（0~1）。
- `scope`: 作用域（domain/task/owner）。
- `created_at` + `ttl`: 时间有效性。
- `branch_id`: 所属分支。
- `sensitivity`: 敏感等级。

### 4.2 MemoryEdge
用于图检索关系建模，支持：
- `supports` / `contradicts` / `derived_from` / `inherited_from` / `caused_by`。

### 4.3 Branch
用于 BranchWorldModel：
- `id`、`name`、`hypothesis`、`parent_id`、`status`。

### 4.4 TaskIntent
运行时查询输入：
- 谁在做什么任务、处于哪个分支、当前请求文本是什么。

## 5. 核心流程（与代码一致）

1. Capture：将候选知识写入 `MemoryAtom`。
2. Retrieval：按时间窗、作用域、分支检索并打分。
3. Graph Expansion：沿图边扩展邻居证据。
4. Governance：按角色策略做选择性披露。
5. Runtime Context：组装可直接注入 Agent 的上下文包。
6. Outcome Feedback：记录任务结果与指标，回写新记忆。

## 6. 可维护性策略

- 领域对象使用 dataclass，减少样板代码。
- 服务层不直接依赖外部框架，便于测试。
- 所有关键行为有测试覆盖：时间窗、治理过滤、OpenClaw 交互链路。
- 示例代码不走“魔法配置”，使用显式装配。

## 7. 版本演进建议

- v0.1（当前）：内存存储 + 规则检索 + 角色治理 + 指标观测。
- v0.2：接入向量索引与图数据库（不改领域接口）。
- v0.3：引入策略学习与自动冲突消解。
