# Replay Benchmark v0.2

> Synthetic fixture; this measures the checked-in replay suite, not production traffic or universal superiority.

## Dataset and method

- Dataset: `privacy-safe-incidents-v1` (9 paired replay cases)
- As-of: `2026-06-19T00:00:00Z`
- Evidence class: `synthetic-development`
- Dataset SHA-256: `ab9588efb544f81407b1263c52a2509f16298d1c2d4ce38eb9af9db5f275c758`
- Frozen label-set SHA-256: `e4fa27f5edfe26ad1fa65eec2554b17651ce228f32f79f91a6bcf2b7848e9862`
- Control: ungoverned recent-context top-k
- Treatment: Attack on Memory retrieval + governance + conflict resolution
- Uncertainty: paired bootstrap, 5000 samples, seed 20260619, 95% interval

## Results

| Metric | Control | Treatment | Delta | 95% CI |
|---|---:|---:|---:|---:|
| Context acceptance rate ↑ | 0.333 | 0.889 | +0.556 | [+0.111, +1.000] |
| Relevant recall ↑ | 0.667 | 0.889 | +0.222 | [-0.222, +0.667] |
| Relevant precision ↑ | 0.333 | 0.889 | +0.556 | [+0.222, +0.833] |
| Unsafe inclusion rate ↓ | 0.500 | 0.000 | -0.500 | [-0.778, -0.222] |
| Conflict exposure rate ↓ | 0.333 | 0.000 | -0.333 | [-0.667, +0.000] |
| Average context size ↓ | 2.000 | 1.000 | -1.000 | [-1.000, -1.000] |

## Reproduce

```bash
make replay-benchmark
```

The JSON artifact includes per-case selected memory IDs for auditability.
