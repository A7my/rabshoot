#!/usr/bin/env bash
# Build a portable Linux .deb (Ubuntu 22.04 base) with Docker. Output: release/RabShoot_<ver>_amd64.deb
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/release"
docker build -t rabshoot-linux-builder "$ROOT/packaging/linux"
docker run --rm \
    -v "$ROOT:/src:ro" -v "$ROOT/release:/out" \
    -v rabshoot-cargo-registry:/opt/cargo/registry \
    -v rabshoot-cargo-target:/build/app/src-tauri/target \
    -v rabshoot-npm-cache:/root/.npm -v rabshoot-pip-cache:/root/.cache/pip \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -e RABSHOOT_GITHUB_CLIENT_ID -e RABSHOOT_GITHUB_APP_SLUG -e RABSHOOT_GITLAB_CLIENT_ID \
    rabshoot-linux-builder
