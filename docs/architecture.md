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

补充约定：
- `metadata.memory_key`：跨分支表示“同一语义槽位”的稳定 key，用于子分支覆盖父分支记忆。
- `metadata.supersedes`：显式声明当前记忆覆盖掉的旧记忆 id 或 key。

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

### 5.1 BranchWorldModel 在检索层的落地

- 检索可沿 `branch -> parent -> main` 追溯分支谱系，而不是只看当前分支。
- 如果子分支与父分支存在同一 `memory_key`，优先保留子分支版本，避免上下文里同时出现旧策略与新策略。
- 如果存在 `metadata.supersedes`，即使 key 不同，也会按显式覆盖规则屏蔽被替代记忆。

### 5.2 矛盾记忆感知

- 图中 `contradicts` 边会参与检索排序，对互相冲突的记忆施加风险降权。
- 运行时 `ContextPacket.diagnostics` 会暴露 `inherited` 和 `contradictions` 计数，方便上层编排器做审计、告警或人工复核。
- `ConflictResolver` 支持三种显式策略：保留并标记、基于检索分数/置信度/证据新鲜度与深度择优、整组隔离。
- 择优策略在证据权威度差距不足时会 fail closed，隔离整组冲突，而不是武断选择。
- 每次处理都会生成 `ConflictDecision`，随 `ContextPacket` 返回所涉记忆、结果、胜出项和理由。

### 5.3 生命周期与污染恢复

- `MemoryLifecycleService` 用显式状态机管理 `active / quarantined / superseded / expired / forgotten`，非法迁移默认拒绝。
- 检索与 SQLite 向量直查只允许 `active` 记忆；隔离、整合和过期会立即退出上下文候选。
- 整合产生 `derived_from` 审计边，并要求摘要显式声明全部 `supersedes` 来源。
- 遗忘在同一事务中写入内容最小化审计事件，再物理删除 claim、evidence、graph edge 与 vector；遗忘状态不可恢复。
- 污染恢复可沿 `derived_from / caused_by` 邻域保守隔离，等待复核后逐项恢复。

### 5.4 目的绑定与治理审计

- `DisclosurePolicy` 可要求显式 `TaskIntent.purpose`，并限制允许目的；合法角色不等于任意用途都可读取。
- 每个候选记忆产生带 `policy_id / version / reason_code` 的 `GovernanceDecision`，允许与拒绝都可复盘。
- 完整策略决策进入独立 `GovernanceAuditSink`；Agent 的 `ContextPacket` 只携带审计 ID 和聚合计数，避免策略拒绝解释侧漏 atom 身份。
- SQLite v4 持久化不可变 `(request_id, atom_id)` 决策，审计在进程重启和记忆遗忘后仍可保留。
- 策略注册禁止静默覆盖；更新必须匹配当前 ID/版本并严格 `+1`。
- `policy-check` 静态检查危险组合；what-if 在相同样本上成对比较新旧策略，并可阻断任何新增披露。
- 治理审计可导出为逐记录 SHA-256 哈希链，并用组织内 HMAC 或可外部验签的 Ed25519 签署根清单。

## 6. 可维护性策略

- 领域对象使用 dataclass，减少样板代码。
- 服务层依赖 `MemoryStore` 行为协议，不绑定内存或数据库实现。
- `SQLiteStore` v4 持久化 atom、edge、branch、vector、生命周期事件与治理决策，提供显式 schema 迁移、WAL、完整同步、嵌套事务 savepoint、并发写串行化与重启恢复。
- 在线备份经过 SQLite 一致性快照、完整性校验、文件 fsync 与原子发布；恢复同样先校验再原子替换，并拒绝带活动 WAL sidecar 的目标。
- `TextEmbedder` 是可替换边界；`HashingTextEmbedder` 只提供确定性的零依赖本地基线，生产部署应注入经过验证的语义 embedding 模型。
- 内存与 SQLite 后端运行同一套契约测试，确保分支继承顺序、图遍历和检索结果语义一致。
- 所有关键行为有测试覆盖：时间窗、治理过滤、分支继承覆盖、冲突感知、OpenClaw 交互链路。
- 示例代码不走“魔法配置”，使用显式装配。

## 7. 版本演进建议

- v0.1（当前）：内存存储 + 规则检索 + 角色治理 + 指标观测。
- v0.2：接入向量索引与图数据库（不改领域接口）。
- v0.3：引入策略学习与自动冲突消解。
