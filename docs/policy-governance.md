# Policy Governance

Disclosure policies are deployment artifacts, not anonymous runtime dictionaries.
Give every policy a stable `policy_id`, increment `version` exactly once per
change, and use explicit purpose binding for operational access.

## Static lint

```bash
make policy-check
```

The checker fails on ambiguous registrations and unsafe logical combinations.
Warnings identify broad policies such as wildcard scope, unbound purpose,
zero-confidence admission, or secret disclosure. Red-team scenarios may retain
warnings intentionally; production policy sets should review or eliminate them.

## What-if rollout gate

`compare_policy_change(current, candidate, samples)` evaluates both versions on
the same `(request, memory)` samples and reports only opaque request/atom IDs and
reason codes—never claims. `assert_no_permission_expansion(report)` fails when a
candidate newly allows any sampled disclosure.

Policy updates are optimistic and monotonic:

```python
governor.update_policy(
    candidate,
    expected_policy_id="ops-recovery",
    expected_version=7,
)
```

An update cannot silently replace a role, change policy identity, skip a version,
or roll back to an older version.

## Remaining trust boundary

The decision database is immutable at the application level and included in
SQLite integrity/backup checks. It is not yet cryptographically signed; export to
an append-only external audit system remains a production qualification item.
