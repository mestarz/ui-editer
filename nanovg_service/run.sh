#!/usr/bin/env bash
# run.sh — 启动 Express(3002) + Vite(5174)，或 -s 停止
#
# 用法:
#   ./run.sh               启动；按需自动 build C 渲染器与 npm install
#   ./run.sh -s            停止后台进程
#   ./run.sh --status      查看进程状态
#   ./run.sh --rebuild     强制重新编译 C 渲染器
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PID_DIR="$ROOT/.run"; mkdir -p "$PID_DIR"
SRV_PID="$PID_DIR/server.pid"; WEB_PID="$PID_DIR/vite.pid"
SRV_LOG="$PID_DIR/server.log"; WEB_LOG="$PID_DIR/vite.log"

stop_one() {
  local pf="$1" name="$2"
  if [[ -f "$pf" ]]; then
    local pid; pid="$(cat "$pf")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true; sleep 0.5; kill -9 "$pid" 2>/dev/null || true
      echo "[stop] $name (pid=$pid)"
    fi
    rm -f "$pf"
  fi
}
cmd_stop()   { stop_one "$SRV_PID" express; stop_one "$WEB_PID" vite; }
cmd_status() {
  for pair in "express:$SRV_PID" "vite:$WEB_PID"; do
    name="${pair%%:*}"; pf="${pair##*:}"
    if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null
      then echo "$name: running (pid=$(cat "$pf"))"
      else echo "$name: stopped"
    fi
  done
}

ACTION=start; REBUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--stop) ACTION=stop; shift ;;
    --status)  ACTION=status; shift ;;
    --rebuild) REBUILD=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done
[[ "$ACTION" == stop   ]] && { cmd_stop; exit 0; }
[[ "$ACTION" == status ]] && { cmd_status; exit 0; }

# C renderer
BIN="$ROOT/renderer/build/nvg_renderer"
if [[ ! -x "$BIN" || "$REBUILD" -eq 1 ]]; then
  echo "[run] building C renderer..."
  "$ROOT/build.sh"
fi

# npm install
if [[ ! -d node_modules ]]; then
  echo "[run] running npm install..."
  npm install
fi

cmd_stop
nohup node server/index.js > "$SRV_LOG" 2>&1 & echo $! > "$SRV_PID"
nohup npx vite --host  > "$WEB_LOG" 2>&1 & echo $! > "$WEB_PID"
sleep 1
echo "[run] express  pid=$(cat "$SRV_PID")  log=$SRV_LOG"
echo "[run] vite     pid=$(cat "$WEB_PID")  log=$WEB_LOG"
echo "[run] open http://localhost:5174/"
echo "[run] stop with: ./run.sh -s"
