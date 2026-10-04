#!/usr/bin/env bash
# Runs inside the container: /src is the repo (read-only), /out receives the .deb.
set -euo pipefail

rsync -a --delete /src/ /build/ \
    --exclude .venv --exclude .rabshoot-dev --exclude release --exclude node_modules \
    --exclude app/dist --exclude app/src-tauri/target --exclude app/src-tauri/binaries \
    --exclude app/src-tauri/gen --exclude engine/build --exclude engine/dist --exclude .env
cd /build

python3.12 -m venv /venv
/venv/bin/pip install -q --upgrade pip
/venv/bin/pip install -q -e "engine[dev]"
/venv/bin/python scripts/build_engine.py

cd app
npm ci --no-audit --no-fund
npx tauri build --bundles deb

deb=$(ls -t src-tauri/target/release/bundle/deb/*.deb | head -1)
install -m 0644 "$deb" /out/
chown "${HOST_UID:-0}:${HOST_GID:-0}" "/out/$(basename "$deb")" 2>/dev/null || true
echo "Built: /out/$(basename "$deb")"
