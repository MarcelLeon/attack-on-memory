# Social Waves (48H) — CN + EN

## Wave 1 (Now) — Launch Positioning

### CN
我们开源了 **Attack on Memory**。  
它不是 RAG 套壳，而是 **多 Agent 记忆治理层**：
- 可验证的 Memory Atom
- 按角色/敏感度选择性披露
- 可审计的引用链与评估闭环

仓库：https://github.com/MarcelLeon/attack-on-memory

### EN
We open-sourced **Attack on Memory**.
It’s not a RAG wrapper, but a **memory governance layer for multi-agent systems**:
- verifiable memory atoms
- role/sensitivity-based selective disclosure
- auditable citations + evaluation loop

Repo: https://github.com/MarcelLeon/attack-on-memory

---

## Wave 2 (T+24h) — Evidence Drop

### CN
我们发布了第一版可复现实验快照：
- 在 selective disclosure 场景中，guarded 方案相对 baseline：
  - task_success_rate +1.00
  - conflict_rate -1.00
  - contamination_rate -1.00
  - token_cost -150

复现命令与数据：
`docs/benchmarks/v0.1-benchmark-snapshot.md`

### EN
We published a reproducible benchmark snapshot.
In selective disclosure scenario, guarded vs baseline shows:
- task_success_rate +1.00
- conflict_rate -1.00
- contamination_rate -1.00
- token_cost -150

Repro + data:
`docs/benchmarks/v0.1-benchmark-snapshot.md`

---

## Wave 3 (T+48h) — Community Call

### CN
接下来我们优先做：
1) graph backend adapter
2) replay-driven benchmark expansion
3) stronger anti-poisoning policies

欢迎认领 issue：
https://github.com/MarcelLeon/attack-on-memory/issues

### EN
Next priorities:
1) graph backend adapter
2) replay-driven benchmark expansion
3) stronger anti-poisoning policies

Contributions welcome:
https://github.com/MarcelLeon/attack-on-memory/issues
