# 实验设计与现实交互价值验证（以 OpenClaw 为例）

## 1. 目标

验证这套框架是否真正提升 OpenClaw 的记忆管理能力，而不是只增加复杂度。

## 2. 实验框架

### 2.1 实验组与对照组
- 对照组：OpenClaw 仅使用最近对话上下文（无结构化记忆）。
- 实验组：接入 Agent Memory Framework（检索 + 治理 + 回写）。

### 2.2 三阶段验证
1. 离线回放：历史任务重放，比较命中率和重复错误率。
2. 在线灰度：真实流量 A/B，比较任务成功率、平均耗时、token 成本。
3. 压力与污染注入：引入错误记忆，验证隔离、降权、回滚能力。

## 3. 关键指标（与代码一致）

- `hit_rate`: 检索命中率。
- `task_success_rate`: 任务成功率。
- `repeat_error_rate`: 重复错误率。
- `conflict_rate`: 记忆冲突率。
- `contamination_rate`: 记忆污染率。
- `avg_latency_ms`: 平均延迟。
- `avg_token_cost`: 平均 token 成本。

指标实现见 `src/attack_on_memory/evals/metrics.py`。

## 4. 现实应用交互（如何体现价值）

### 4.1 人机协作闭环
- 人类 reviewer 对任务结果打标（成功/失败/风险）。
- 框架把打标转为记忆质量反馈，调整后续检索优先级。

### 4.2 业务流程嵌入
- 在 OpenClaw 的任务前置阶段自动注入上下文。
- 在任务后置阶段自动回写经验与异常。
- 对敏感任务强制启用治理策略审计。

### 4.3 价值呈现方式
- 给管理者：看成功率、重复错误率、交接耗时变化。
- 给开发者：看具体 `atom_id` 的引用链与失败回溯。
- 给安全团队：看披露策略命中与越权拦截统计。

## 5. 建议里程碑

1. 第 1 周：接入 `OpenClawMemoryAdapter`，跑通上下文注入与结果回写。
2. 第 2 周：完成离线回放基线，产出第一版指标看板。
3. 第 3-4 周：上线 10%-20% 灰度流量，验证收益与副作用。
4. 第 5 周：优化策略（冲突处理、分支选择、TTL 调参）。

## 6. 预期收益（初始假设）

- 重复错误率下降 20%~40%。
- 任务交接冷启动时间下降 30%+。
- 在复杂任务上任务成功率提升 8%~15%。

以上为假设值，必须通过真实 A/B 数据验证。

## 7. 剧情线仿真实验（可执行）

为展示理论闭环与工程价值，增加了 3 个可执行 scenario spec：

- `examples/scenarios/case_01_selective_disclosure_manipulation.json`：
  选择性披露红队攻击（格里沙操纵尝试，含 baseline/permissive 与 guarded 对照）。
- `examples/scenarios/case_02_scout_inheritance.json`：
  调查兵团作战继承（团长经验向阿尔敏与执行队传递）。
- `examples/scenarios/case_03_rumbling_emergency_privilege.json`：
  “地鸣级”紧急态权限提升（平时最小权限、应急受控放权、分支效用比较）。

执行方式：

```bash
PYTHONPATH=src python examples/simulation_runner.py
```

可选输出 JSON 报告：

```bash
PYTHONPATH=src python examples/simulation_runner.py --json-output /tmp/aom-results.json
```

从 OpenClaw 回放日志生成场景（用于真实数据闭环）：

```bash
PYTHONPATH=src python examples/openclaw_replay_to_scenario.py \
  --replay /path/to/replay.jsonl \
  --output /tmp/replay_scenario.json \
  --scenario-id openclaw_replay_demo
```
