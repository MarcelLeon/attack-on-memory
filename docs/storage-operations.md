# Storage Operations

`SQLiteStore` is the durable single-node backend. It uses WAL, `synchronous=FULL`,
foreign keys, schema migrations, and a 5-second busy timeout.

## Verify

```python
from attack_on_memory import SQLiteStore

with SQLiteStore("memory.db") as store:
    evidence = store.verify_integrity()
    print(evidence)
```

`verify_integrity()` runs SQLite's full integrity check and returns schema, atom,
edge, branch, vector, lifecycle-event, and governance-decision counts. Treat any exception as a failed
readiness gate.

## Online backup

```python
with SQLiteStore("memory.db") as store:
    store.backup_to("backups/memory-2026-06-19.db")
```

The backup API uses SQLite's online backup mechanism, validates the generated
database, fsyncs it, and publishes it atomically. It refuses to overwrite by
default and refuses destinations with WAL sidecars, which may indicate a live
database.

## Restore

Stop writers before replacing a primary database. Restore first verifies the
source backup, copies it to a temporary database, verifies the copy, and then
publishes it atomically.

```python
recovered = SQLiteStore.restore_from(
    "backups/memory-2026-06-19.db",
    "memory.db",
    overwrite=True,
)
try:
    print(recovered.verify_integrity())
finally:
    recovered.close()
```

## Qualification boundary

The checked-in contract suite covers concurrent threads, four independent writer
processes, online snapshot consistency, restart recovery, schema migration, and
recovery over a deliberately corrupted primary. It does not yet establish a
production throughput envelope, network-filesystem safety, geo-replication, or
the quality of a production embedding model.

Run the executable target-environment gate described in
[`runtime-qualification.md`](runtime-qualification.md) to measure the throughput
envelope, exercise a named semantic provider, and bind backup-retention evidence.
