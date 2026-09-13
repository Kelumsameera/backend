#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
export PYTHONPATH=.
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-3000}"
