#!/usr/bin/env bash
# build.sh — 前端 vite build
set -euo pipefail
cd "$(dirname "$0")"
[[ -d node_modules ]] || npm install
npx vite build
echo "[build] done. output: dist/"
