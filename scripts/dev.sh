#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

(cd backend && exec .venv/bin/uvicorn travel_agent.api.app:app --reload --port 8000) &
API_PID=$!

(cd frontend && exec pnpm dev) &
WEB_PID=$!

cleanup() {
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo ""
echo "API: http://127.0.0.1:8000/docs"
echo "Web: http://127.0.0.1:5173"
echo ""

wait
