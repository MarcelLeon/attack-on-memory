# Attack on Memory — Enterprise Review Checklist (Launch-Ready)

## 1) Product Narrative & Positioning
- [ ] One-line value proposition is concrete and testable.
- [ ] Problem framing includes measurable pain (handoff failure, repeat errors, memory contamination).
- [ ] Differentiation vs vanilla RAG is explicit (graph+time-window+governance+branch world model).
- [ ] README contains 3 audience paths: builder / security / operator.

## 2) Architecture Correctness
- [ ] Domain invariants are documented and tested.
- [ ] Time-aware semantics (`ttl`, `lookback`) have deterministic tests.
- [ ] Graph retrieval edges are validated and auditable.
- [ ] Governance policy has deny-by-default behavior for sensitive roles.

## 3) Security & Trust
- [ ] Threat model written (memory poisoning / privilege fusion / leakage).
- [ ] SECURITY.md includes disclosure and SLA.
- [ ] Branch protections + required checks configured in GitHub.
- [ ] Scorecard + Dependabot enabled.

## 4) Reliability & Operability
- [ ] CI runs on supported Python versions.
- [ ] Scenario schema + semantic validator are part of release gate.
- [ ] Failure modes are documented (stale memory, contradictory evidence, absent policy).
- [ ] Metrics can support postmortem-level analysis.

## 5) Evaluation Quality
- [ ] Baseline vs guarded variants are demonstrated.
- [ ] Metrics include hit/success/repeat-error/conflict/contamination/latency/cost.
- [ ] At least one replay-derived scenario is published.
- [ ] Benchmarks are reproducible with command snippets.

## 6) Open-Source Readiness
- [ ] CONTRIBUTING / CODE_OF_CONDUCT / PR template / issue templates added.
- [ ] LICENSE present and aligned with dependency licenses.
- [ ] Versioning and release policy documented.
- [ ] "Good first issue" and roadmap labels prepared.

## 7) Viral Launch Potential (GitHub)
- [ ] README has visual architecture + quickstart in < 3 minutes.
- [ ] Includes side-by-side “without vs with framework” outputs.
- [ ] Provides red-team demo scenario that is easy to run.
- [ ] Includes “why this matters now” section linked to agent reliability trend.

## 8) First 30 Days Execution
- [ ] Week 1: polish docs + CI + examples reproducibility.
- [ ] Week 2: publish benchmark report and baseline numbers.
- [ ] Week 3: launch article + community demo recording.
- [ ] Week 4: gather issues, ship v0.2 plan from real feedback.
