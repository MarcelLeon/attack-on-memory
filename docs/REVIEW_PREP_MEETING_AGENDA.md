# Review Meeting Agenda (Code + Design)

## 目标
在 45-60 分钟内完成一次“可上线前”的架构与代码 review，对齐 v0.2 方向。

## 会前材料
- README
- docs/architecture.md
- docs/experiments-and-value.md
- docs/ENTERPRISE_REVIEW_CHECKLIST.md

## 议程
1. 10 min — 问题定义与定位（为何不是 RAG wrapper）
2. 15 min — 代码 walkthrough（domain → retrieval → governance → runtime）
3. 10 min — 风险评审（poisoning / privilege fusion / leakage）
4. 10 min — 评估闭环（指标、scenario、回放）
5. 10 min — v0.2 取舍（vector/graph backends + strategy tuning）

## 决策输出（会后必须明确）
- [ ] 是否按 v0.1.0 对外发布
- [ ] v0.1.1 快速修复项
- [ ] v0.2 三个最高优先级
- [ ] 谁负责 benchmark 与社区反馈处理
