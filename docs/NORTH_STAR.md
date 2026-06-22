# North Star

## North-star metric

**Governed Context Acceptance Rate** measures whether a labeled replay receives a complete and safe context:

```text
governed_context_acceptance_rate =
  replay contexts with all required memories,
  no forbidden memories, and no exposed contradiction
  / labeled replay contexts
```

This is intentionally stricter than retrieval hit rate. It requires human labels, so the checked-in synthetic replay is only development evidence; sanitized execution-derived replay is still required for production claims.

Scenario diagnostics also report `governed_safe_projection_rate`: policy-approved,
non-conflict-flagged projections divided by retrieved candidates. That metric is an
unlabeled safety proxy and is deliberately not called “useful.”

## Problem solved

Long-running agents do not only forget things. They also remember the wrong things:

- stale memories keep influencing future decisions
- sensitive memories leak across roles
- conflicting memories enter the same context
- branch-specific plans inherit obsolete parent assumptions
- vector similarity is treated as evidence even when provenance is weak

Attack on Memory turns memory from an ungoverned recall cache into an auditable context layer. Every injected memory can be scoped, time-bounded, cited, filtered by role, inherited by branch, overridden by child branches, and flagged when it conflicts with another retrieved memory.

## Fast experience

Run the north-star report:

```bash
make north-star
```

The report executes the labeled replay and scenario suites and prints:

- governed context acceptance rate and evidence scope
- governed safe projection proxy
- governed context pass rate
- scenario pass rate
- projected, redacted, inherited, and conflict-flagged memory counts
- scenario proof points for selective disclosure, branch inheritance, and emergency privilege

For lower-level checks:

```bash
make test
make validate-scenarios
PYTHONPATH=src python3 examples/simulation_runner.py
```

## What users should notice first

### Selective disclosure

`case_01_selective_disclosure_manipulation` shows the same candidate memory pool under permissive and guarded policies. The guarded variant redacts risky memories before they enter the runtime packet.

### Branch inheritance

`case_02_scout_inheritance` shows a child branch inheriting useful parent memories while overriding an obsolete parent memory through `metadata.memory_key`.

### Emergency privilege

`case_03_rumbling_emergency_privilege` shows normal least-privilege behavior first, then controlled emergency expansion with citations and diagnostics.

## Differentiation

| Category | Common emphasis | Attack on Memory emphasis |
|---|---|---|
| Vector memory | Retrieve semantically similar facts | Decide whether retrieved memory is safe and useful |
| Agent runtime memory | Keep an agent stateful over time | Govern what can enter an agent's context |
| Graph memory | Model relationships between facts | Use relationships for evidence, inheritance, and conflict signals |
| Enterprise memory | Store and search organizational knowledge | Enforce role, sensitivity, branch, TTL, and citation constraints |

The project sentence:

> Attack on Memory is not memory that remembers more; it is memory that agents are allowed to trust.
