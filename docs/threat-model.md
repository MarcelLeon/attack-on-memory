# Threat Model (v0.1 draft)

## Scope
Attack on Memory memory protocol components:
- memory capture
- retrieval (time-window + graph expansion)
- governance projection
- runtime context injection
- feedback writeback

## Assets
- Memory atoms (claims/evidence/confidence/scope)
- Sensitive evidence references
- Governance policies by role
- Runtime context packet and citations

## Trust Boundaries
1. External input → Capture pipeline
2. Store/index → Retrieval service
3. Retrieval output → Governance policy
4. Governance projection → Runtime agent context
5. Runtime outcome → Writeback/eval metrics

## Primary Threats

### 1) Memory poisoning
**Vector:** adversarial or low-quality claims are captured and later retrieved as if trustworthy.

**Mitigations (v0.1):**
- atom confidence field
- evidence references required
- ttl/lookback filters
- scenario validation and replay-based testing

**Gaps:**
- no cryptographic provenance
- no reputation system for sources

### 2) Over-disclosure / data leakage
**Vector:** sensitive atoms exposed to roles that should only receive summarized projections.

**Mitigations (v0.1):**
- sensitivity levels
- role-based selective disclosure policy
- auditable citations in runtime packet

**Gaps:**
- policy misconfiguration risk
- no policy simulation dashboard yet

### 3) Privilege fusion
**Vector:** combining high-level planning and high-sensitivity read paths into effectively unrestricted authority.

**Mitigations (v0.1):**
- role-scoped governance checks
- scenario tests modeling emergency and manipulation cases

**Gaps:**
- no break-glass workflow with mandatory dual-approval yet

### 4) Stale or contradictory memory use
**Vector:** expired or conflicting atoms influence decisions.

**Mitigations (v0.1):**
- TTL and lookback filtering
- contradiction/support graph edges
- conflict metrics

**Gaps:**
- no automatic conflict resolution strategy learning yet

## Abuse Cases
- Malicious operator injects fabricated evidence links.
- Executor role receives restricted raw evidence by policy bug.
- Emergency mode quietly persists elevated access after incident.

## Detection Signals
- contamination_rate spike
- conflict_rate spike
- unusual increase in sensitive projection counts
- repeated error signatures post-memory updates

## Immediate Hardening Backlog
1. Provenance signatures for evidence records.
2. Policy lint + simulation before deployment.
3. Break-glass controls (time-boxed, dual-approval, full audit).
4. Source trust weighting in retrieval ranking.

## References
- SECURITY.md
- docs/ENTERPRISE_REVIEW_CHECKLIST.md
- examples/scenarios/*
