# OpenClaw 对接设计（Agent Memory Framework v0.1）

## 1. 目标受众定义

OpenClaw 作为多 Agent 协作系统，常见痛点是：
- 任务交接后上下文断裂。
- 历史错误重复发生。
- 敏感信息要么泄漏，要么过度屏蔽。
- A/B 方案比较缺少可追踪证据链。

本框架为 OpenClaw 提供“可寻址 + 可治理 + 可回写”的记忆层。

## 2. 对接点

### 2.1 输入事件（从 OpenClaw 到框架）
`OpenClawTaskEvent`
- `task_id`: 任务 ID。
- `role`: 当前执行角色（planner/executor/reviewer 等）。
- `domain` / `task`: 任务领域与子任务。
- `objective`: 当前目标描述。
- `branch_id`: 所在分支。

### 2.2 输出结果（从框架到 OpenClaw）
`ContextPacket`
- 经过检索与治理后的记忆投影。
- 每条记忆带 `atom_id` 与 `score`，可审计与回溯。

### 2.3 回写事件（从 OpenClaw 到框架）
`record_outcome`
- 任务是否成功。
- 延迟、token 成本。
- 是否出现冲突/污染。
- 新增候选记忆原子。

## 3. 交互序列（简化）

1. OpenClaw 触发任务执行。
2. 调用 `OpenClawMemoryAdapter.build_context` 获取记忆上下文。
3. Agent 执行任务并引用记忆。
4. OpenClaw 回调 `record_outcome` 记录结果并更新指标。
5. 成功经验/失败教训被标准化为 `MemoryAtom`。

## 4. 能力提升点（针对 OpenClaw）

- 记忆稳定性：跨 Agent、跨会话保留可验证经验。
- 交接效率：新 Agent 直接继承高质量证据链。
- 风险控制：通过角色策略进行选择性披露。
- 调试效率：每个建议都能回溯到具体 `atom_id`。
- 分支决策：支持“方案 A/B”并行验证与回注。

## 5. 可落地场景示例

### 5.1 工单/任务自动化
- 复用历史处置步骤，降低重复排障成本。

### 5.2 长周期项目协作
- 保留关键设计决策与反例，减少团队认知漂移。

### 5.3 安全与合规
- 执行 Agent 只拿必要阈值，不拿原始敏感证据。

## 6. 与代码映射

- 事件模型：`src/attack_on_memory/runtime/openclaw_adapter.py`
- 上下文装配：`src/attack_on_memory/runtime/context.py`
- 检索服务：`src/attack_on_memory/application/services.py`
- 治理策略：`src/attack_on_memory/governance/policies.py`
- 指标观测：`src/attack_on_memory/evals/metrics.py`
