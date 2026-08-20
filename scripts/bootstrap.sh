#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[daifuku,dev]'
.venv/bin/python -m playwright install chromium
.venv/bin/pokesleep-score doctor

echo 'Ready. Run: .venv/bin/pokesleep-score demo'
