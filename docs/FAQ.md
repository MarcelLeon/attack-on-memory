# FAQ

## 1) Is this just another RAG wrapper?
No. Attack on Memory focuses on **memory governance for multi-agent systems**:
- Addressable memory units
- Evidence-linked retrieval
- Role/sensitivity-based selective disclosure
- Branch world model for explicit alternatives

## 2) What is a Memory Atom?
A minimal verifiable memory unit:
`claim + evidence + source + confidence + scope + time + ttl + branch_id`.

## 3) How do you reduce stale memory risk?
By combining:
- TTL expiry
- lookback time-window retrieval
- branch-aware filtering

## 4) How do you prevent over-disclosure?
Through governance policies that project memory by role and sensitivity (deny-by-default for restricted roles).

## 5) How do you audit decisions?
Runtime packets include citations (`atom_id`, score, reason) so decisions can be traced back to evidence.

## 6) How do you evaluate quality?
Built-in metrics include:
`hit_rate`, `task_success_rate`, `repeat_error_rate`, `conflict_rate`, `contamination_rate`, latency, token cost.

## 7) Can this integrate with OpenClaw?
Yes. v0.1 includes an adapter for context injection + outcome writeback.

## 8) Is there a benchmark?
Use scenario simulation and replay conversion as baseline. A formal replay-driven benchmark report template is in `docs/BENCHMARK_REPORT_TEMPLATE.md`.

## 9) Is this production-ready?
v0.1 is a solid foundation (tests, scenarios, governance, CI), but backends are in-memory and retrieval is rule-based.

## 10) What’s next?
v0.2 priorities:
- vector index adapter
- graph DB adapter
- stronger anti-poisoning governance
