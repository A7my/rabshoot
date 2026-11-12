#!/usr/bin/env bash
# Dev helper: start engine (dev token, no catch-up) + built UI, run a command, stop both.
# Usage: scripts/ui_session.sh <RABSHOOT_HOME> <command...>
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$1"
HOME_DIR="$(cd "$1" && pwd)"; shift
export RABSHOOT_HOME="$HOME_DIR" RABSHOOT_SECRETS=file PYTHONPATH="$ROOT/engine"
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/.rabshoot-dev/browsers"
"$ROOT/.venv/bin/python" -m rabshoot_engine serve --port 8765 --token dev --no-catch-up >"$HOME_DIR/engine.out" 2>&1 &
ENGINE=$!
(cd "$ROOT/app" && exec npx vite preview --port 4173 --strictPort >"$HOME_DIR/preview.out" 2>&1) &
UI=$!
trap 'kill $ENGINE $UI 2>/dev/null; pkill -P $UI 2>/dev/null' EXIT
for _ in $(seq 1 40); do
  curl -sf -o /dev/null http://localhost:4173/ && curl -sf -o /dev/null -H "Authorization: Bearer dev" http://127.0.0.1:8765/health && break
  sleep 0.5
done
"$@"
