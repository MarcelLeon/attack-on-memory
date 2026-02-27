# Social Launch Posts (X / Reddit / HN)

## X（中文，短版）
我们开源了 **Attack on Memory**：
一个给多 Agent 系统用的“记忆协议层”，不是 RAG 套壳。

核心：
- Addressable / Referable / Inheritable memory
- Selective disclosure（按角色披露）
- Time-window + Graph retrieval
- Branch world model（反事实分支）

目标：减少重复错误、提升交接质量、让记忆可审计。  
Repo: <https://github.com/MarcelLeon/attack-on-memory>

## X（英文，短版）
We open-sourced **Attack on Memory** — a memory protocol layer for multi-agent systems (not another RAG wrapper).

- Addressable / Referable / Inheritable memory
- Selective disclosure by role
- Time-window + graph retrieval
- Branch world model for counterfactuals

Goal: fewer repeated mistakes, better handoffs, auditable decisions.
Repo: <https://github.com/MarcelLeon/attack-on-memory>

## Reddit（r/MachineLearning 风格）
Title: [Project] Attack on Memory: a governable memory protocol for multi-agent systems

Body:
We built a docs-first framework focused on a practical pain point in agent systems: memory reliability over time.

What we implemented in v0.1:
1. Memory atoms with evidence, confidence, scope, TTL
2. Retrieval with time-window filtering + graph expansion
3. Governance with role/sensitivity-based selective disclosure
4. Branch world model for explicit counterfactual branches
5. Scenario spec + validator + replay converter for reproducible evaluation

Would love feedback on:
- threat models (poisoning / privilege fusion)
- benchmark design
- integration priorities for v0.2 (vector + graph backends)

Repo: https://github.com/MarcelLeon/attack-on-memory

## Hacker News（Show HN）
Title: Show HN: Attack on Memory — a memory governance layer for multi-agent systems

Post:
I built Attack on Memory to address a recurring failure mode in agent systems: memory is either over-shared, stale, or not auditable.

This project introduces a protocol-oriented memory layer:
- addressable memory atoms
- evidence-linked retrieval
- role-based selective disclosure
- branch world model for comparing alternatives

It includes a minimal OpenClaw adapter and scenario-based validation workflow.

I’m looking for critical feedback on evaluation rigor and production hardening priorities.

Repo: https://github.com/MarcelLeon/attack-on-memory
