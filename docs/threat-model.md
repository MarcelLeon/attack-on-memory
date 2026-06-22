# Threat Model (v0.2)

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

**Mitigations:**
- atom confidence field
- evidence references required
- ttl/lookback filters
- scenario validation and replay-based testing
- fail-closed quarantine with immutable, content-minimized lifecycle events
- derivation-neighborhood quarantine for contamination recovery

**Gaps:**
- no cryptographic provenance
- no reputation system for sources

### 2) Over-disclosure / data leakage
**Vector:** sensitive atoms exposed to roles that should only receive summarized projections.

**Mitigations:**
- sensitivity levels
- role-based selective disclosure policy
- explicit purpose binding for sensitive workflows
- versioned allow/deny reason codes in a separate audit plane
- auditable citations in runtime packet

**Gaps:**
- policy misconfiguration risk
- no static policy lint or what-if simulation yet

### 3) Privilege fusion
**Vector:** combining high-level planning and high-sensitivity read paths into effectively unrestricted authority.

**Mitigations:**
- role-scoped governance checks
- scenario tests modeling emergency and manipulation cases

**Gaps:**
- no break-glass workflow with mandatory dual-approval yet

### 4) Stale or contradictory memory use
**Vector:** expired or conflicting atoms influence decisions.

**Mitigations:**
- TTL and lookback filtering
- contradiction/support graph edges
- conflict metrics
- evidence-aware select-or-quarantine conflict resolution
- explicit consolidation and TTL expiry lifecycle states

**Gaps:**
- resolution weights are not calibrated on execution-derived incidents yet

### 5) Incomplete erasure
**Vector:** deleting one representation leaves claims, evidence, graph edges, or vectors recoverable elsewhere.

**Mitigations:**
- transactional erasure of atom content with graph/vector cascade
- terminal `forgotten` state prevents accidental recapture under the same id
- content-minimized lifecycle event retains only opaque id, reason code, actor, time, and version

**Gaps:**
- external vector services and backups need adapter-specific erasure attestations
- jurisdiction-specific retention requirements are not yet qualified

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
