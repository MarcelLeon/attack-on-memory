# Attack on Memory

> 面向多 Agent 系统的记忆治理层。

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![CI](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/ci.yml)
[![Scorecard](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/scorecard.yml/badge.svg)](https://github.com/MarcelLeon/attack-on-memory/actions/workflows/scorecard.yml)

## 为什么做这个项目

当 Agent 从单轮问答走向长期协作，瓶颈不再只是模型参数，而是**记忆质量**：
- **可信**：可验证、可追溯
- **可控**：按角色披露、可撤回
- **可演化**：可继承、可回滚、可分支比较

Attack on Memory 不是另一个 RAG 包装器，而是多 Agent 记忆协议层：
**Graph Retrieval + Time-window Retrieval + Governance + BranchWorldModel**。

当前内核最有辨识度的能力：
- 支持父分支记忆继承与子分支覆盖的分支感知检索
- 对矛盾记忆做风险降权，并按策略标记、证据择优或保守隔离，保留完整决策记录
- 事务化 SQLite atom/graph/branch/vector 持久层，支持 schema 迁移与重启恢复
- 可审计生命周期状态机：隔离、整合、过期、物理遗忘与污染恢复
- 目的绑定披露，以及与 Agent 上下文隔离的版本化允许/拒绝审计
- 用场景仿真端到端验证披露、继承、回滚等记忆行为

## 3 分钟快速开始

```bash
# 实时目标、里程碑、交付证据与下一动作
make status

# 0) 北极星报告：这个项目到底解决什么问题？
make north-star

# 1) 单元测试
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 2) 场景校验
PYTHONPATH=src python3 examples/validate_scenarios.py

# 3) 仿真演示
PYTHONPATH=src python3 examples/simulation_runner.py
```

## v0.1 已具备能力

- 领域模型与运行时 memory packet 设计
- 治理策略（选择性披露、紧急权限控制）
- 分支继承与子分支覆盖检索语义
- 可审计的矛盾检测、证据择优与保守隔离
- `MemoryStore` 协议与持久化 SQLite atom、graph、branch、vector 存储
- 默认拒绝的生命周期治理、物理删除与污染邻域隔离
- 目的绑定和可解释治理，策略拒绝的记忆身份不会泄漏到 Agent 上下文
- 场景驱动仿真与校验
- OpenClaw 适配器（上下文注入 + 结果回写）
- CI + Scorecard + Dependabot + 开源治理基线

## 可复现 Benchmark 快照

- 带 95% 置信区间的成对 replay 报告：`docs/benchmarks/replay-v0.2-report.md`
- 隐私安全 replay 样本：`examples/replays/privacy_safe_incidents.json`
- 重现 replay 产物：`make replay-benchmark`
- 基线报告：`docs/benchmarks/v0.1-baseline.md`
- 快照报告：`docs/benchmarks/v0.1-benchmark-snapshot.md`
- 最新原始结果：`docs/benchmarks/latest-results.json`
- 快照生成脚本：`scripts/generate_benchmark_snapshot.py`

## 架构与文档入口

- 实时项目状态：`docs/project-state.json`（运行 `make status`）
- 回放来源、脱敏审查与冻结标签准入：`docs/replay-evidence.md`
- 存储完整性、在线备份与恢复：`docs/storage-operations.md`
- 目标环境吞吐、语义模型与恢复资格门禁：`docs/runtime-qualification.md`（运行 `make qualify-runtime`）
- 策略 lint、版本更新与权限扩张 what-if 门禁：`docs/policy-governance.md`
- 哈希链与 HMAC/Ed25519 签名治理审计：`docs/signed-audit.md`
- 北极星指标与定位：`docs/NORTH_STAR.md`
- 架构说明：`docs/architecture.md`
- 场景规范：`docs/scenario-spec.md`
- 实验与价值：`docs/experiments-and-value.md`
- OpenClaw 集成：`docs/openclaw-integration.md`
- 威胁模型：`docs/threat-model.md`
- 常见问题：`docs/FAQ.md`
- 首次贡献指南：`docs/STARTER_PR_WALKTHROUGH.md`

## 目录结构

- `src/attack_on_memory/domain/` – 领域模型
- `src/attack_on_memory/application/` – 检索与编排
- `src/attack_on_memory/governance/` – 治理策略
- `src/attack_on_memory/runtime/` – 运行时适配与上下文
- `src/attack_on_memory/infrastructure/` – 内存与后端适配
- `examples/` – 场景、校验、仿真
- `tests/` – 单测与适配器接线测试

## 安全与治理

- 安全策略：[`SECURITY.md`](./SECURITY.md)
- 社区行为准则：[`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- 贡献指南：[`CONTRIBUTING.md`](./CONTRIBUTING.md)

## 下一步路线

- 从 scenario-derived 升级到 replay-derived benchmark
- 可插拔向量索引适配
- 可插拔图后端适配
- 更强的抗污染治理与可观测性
- 从“识别冲突”走向“自动冲突消解”的策略层

## 许可证

Apache-2.0
