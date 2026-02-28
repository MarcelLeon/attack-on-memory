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

## 3 分钟快速开始

```bash
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
- 场景驱动仿真与校验
- OpenClaw 适配器（上下文注入 + 结果回写）
- CI + Scorecard + Dependabot + 开源治理基线

## 可复现 Benchmark 快照

- 基线报告：`docs/benchmarks/v0.1-baseline.md`
- 快照报告：`docs/benchmarks/v0.1-benchmark-snapshot.md`
- 最新原始结果：`docs/benchmarks/latest-results.json`
- 快照生成脚本：`scripts/generate_benchmark_snapshot.py`

## 架构与文档入口

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

## 许可证

MIT
