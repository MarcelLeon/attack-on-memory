#!/usr/bin/env bash
set -euo pipefail

# Create a 90s terminal demo GIF if asciinema + agg are installed.
# Usage:
#   scripts/make_demo_gif.sh

if ! command -v asciinema >/dev/null 2>&1; then
  echo "[ERROR] asciinema not found. Install: brew install asciinema"
  exit 1
fi

if ! command -v agg >/dev/null 2>&1; then
  echo "[ERROR] agg not found. Install from: https://github.com/asciinema/agg"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/docs/assets"
mkdir -p "$OUT_DIR"

CAST="$OUT_DIR/demo.cast"
GIF="$OUT_DIR/demo.gif"

cat > "$OUT_DIR/demo-commands.sh" <<'CMD'
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../.."
echo "== Attack on Memory quick demo =="
PYTHONPATH=src python3 examples/validate_scenarios.py
PYTHONPATH=src python3 examples/simulation_runner.py
CMD
chmod +x "$OUT_DIR/demo-commands.sh"

asciinema rec -c "$OUT_DIR/demo-commands.sh" "$CAST"
agg --fps-cap 30 --speed 1.2 "$CAST" "$GIF"

echo "[OK] demo GIF created: $GIF"
