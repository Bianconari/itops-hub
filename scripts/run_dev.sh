#!/usr/bin/env bash
# Development environment setup + run (Linux/macOS/sandbox).
# Windows developers: see README.md for the PowerShell equivalents.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt -r requirements-dev.txt

echo "Environment ready. Running ITOps Hub..."
python -m app.main
