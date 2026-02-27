# Scenario Spec Contract

## 1. 目的

定义可执行实验场景的统一 JSON 合同，确保：
- 场景可复现。
- 断言可验证。
- 回放日志可转换成同一协议。

## 2. Schema 与校验

- JSON Schema：`examples/scenarios/scenario.schema.json`
- 语义校验器：`src/attack_on_memory/scenarios/spec_validation.py`
- 命令：`PYTHONPATH=src python examples/validate_scenarios.py`

## 3. 最小结构

- `schema_version`
- `scenario_id`
- `variants[]`

每个 variant 至少包含：
- `variant_id`
- `policies[]`
- `memories[]`
- `events[]`

## 4. 关键约束

- 每个 event 的 `role` 必须有对应 policy。
- edge 引用的 `source_id/target_id` 必须存在于 memories。
- `metric_assertions.metric` 必须在系统指标白名单内。
- `confidence/success_rate/risk_score/cost_score` 范围必须在 `[0,1]`。

## 5. 回放转场景

- 工具：`examples/openclaw_replay_to_scenario.py`
- 核心实现：`src/attack_on_memory/scenarios/replay_converter.py`

用途：把真实 OpenClaw 运行日志转成 scenario spec，用于离线回放、回归验证和策略调参。
