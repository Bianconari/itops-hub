#!/usr/bin/env bash
# Full local quality gate: format check, lint, types, tests.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true
pip install --quiet -r requirements.txt -r requirements-dev.txt

echo "== ruff format =="
ruff format --check .
echo "== ruff lint =="
ruff check .
echo "== mypy (strict) =="
mypy
echo "== pytest =="
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
pytest -q
echo "== selftest =="
python -m app.main --selftest
echo "ALL GATES PASSED"
