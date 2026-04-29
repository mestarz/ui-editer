#!/usr/bin/env bash
# run.sh — Web Layout Editor 启动脚本
#
# 用法:
#   ./run.sh                                 启动 Express(3001) + Vite(5173)，默认 game-root=../../BaiSiYeShou
#   ./run.sh --game-root /path/to/game       指定主仓库位置
#   ./run.sh -s                              停止后台进程
#   ./run.sh --status                        查看进程状态
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
PID_DIR="$ROOT/.run"
mkdir -p "$PID_DIR"
SRV_PID="$PID_DIR/server.pid"
WEB_PID="$PID_DIR/vite.pid"
SRV_LOG="$PID_DIR/server.log"
WEB_LOG="$PID_DIR/vite.log"

stop_one() {
  local pidfile="$1" name="$2"
  if [[ -f "$pidfile" ]]; then
    local pid; pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.5
      kill -9 "$pid" 2>/dev/null || true
      echo "[stop] $name (pid=$pid)"
    fi
    rm -f "$pidfile"
  fi
}

cmd_stop() {
  stop_one "$SRV_PID" "express"
  stop_one "$WEB_PID" "vite"
}

cmd_status() {
  for pair in "express:$SRV_PID" "vite:$WEB_PID"; do
    name="${pair%%:*}"; pf="${pair##*:}"
    if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
      echo "$name: running (pid=$(cat "$pf"))"
    else
      echo "$name: stopped"
    fi
  done
}

# ---- 参数解析 ----
GAME_ROOT_ARG=""
ACTION="start"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--stop)    ACTION="stop"; shift ;;
    --status)     ACTION="status"; shift ;;
    --game-root)  GAME_ROOT_ARG="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ "$ACTION" == "stop" ]]; then cmd_stop; exit 0; fi
if [[ "$ACTION" == "status" ]]; then cmd_status; exit 0; fi

# ---- 启动 ----
DEFAULT_ROOT="$(cd "$ROOT/../../BaiSiYeShou" 2>/dev/null && pwd || echo "")"
GAME_ROOT="${GAME_ROOT_ARG:-$DEFAULT_ROOT}"
if [[ -z "$GAME_ROOT" || ! -d "$GAME_ROOT/scripts" ]]; then
  echo "ERROR: game root not found: '$GAME_ROOT'" >&2
  echo "       use --game-root <path> to specify" >&2
  exit 1
fi
GAME_ROOT="$(cd "$GAME_ROOT" && pwd)"
echo "[run] GAME_ROOT=$GAME_ROOT"

if [[ ! -d node_modules ]]; then
  echo "[run] running npm install..."
  npm install
fi

# 已在跑就先停
cmd_stop

export GAME_ROOT
nohup node server/index.js > "$SRV_LOG" 2>&1 &
echo $! > "$SRV_PID"
nohup npx vite --host > "$WEB_LOG" 2>&1 &
echo $! > "$WEB_PID"

sleep 1
echo "[run] express  pid=$(cat "$SRV_PID")  log=$SRV_LOG"
echo "[run] vite     pid=$(cat "$WEB_PID")  log=$WEB_LOG"
echo "[run] open http://localhost:5173/"
echo "[run] stop with: ./run.sh -s"
