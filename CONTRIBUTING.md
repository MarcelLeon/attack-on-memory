# Contributing to Attack on Memory

Thanks for contributing.

## Dev setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quality gate

```bash
make test
make validate-scenarios
make quality-gate
```

## Contribution standards

1. Keep domain model changes explicit and documented.
2. Add tests for new behavior.
3. For governance changes, include at least one red-team scenario.
4. Update docs (`README.md`, `docs/*`) when behavior changes.
5. Prefer small PRs with clear rollback paths.

## Commit message style

Use concise, imperative commits:
- `feat(governance): add role-based disclosure override`
- `test(scenarios): add contradiction edge validation case`
