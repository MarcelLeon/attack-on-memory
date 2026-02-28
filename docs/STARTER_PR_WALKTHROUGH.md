# Starter PR Walkthrough

This guide helps first-time contributors land a small PR safely.

## 1) Pick an issue
Choose one labeled `good first issue`.

## 2) Setup
```bash
git clone https://github.com/MarcelLeon/attack-on-memory.git
cd attack-on-memory
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 3) Create branch
```bash
git checkout -b feat/<short-topic>
```

## 4) Implement minimal change
Keep PR focused and small. Update docs when behavior changes.

## 5) Run quality gate
```bash
make quality-gate
```

## 6) Commit and push
```bash
git add -A
git commit -m "feat(scope): short summary"
git push origin feat/<short-topic>
```

## 7) Open PR
- Explain **what** changed
- Explain **why**
- Link issue number
- Paste test output

## Review checklist
- [ ] Tests pass
- [ ] Scenario validation passes
- [ ] Docs updated
- [ ] No unrelated changes
