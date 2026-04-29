#!/usr/bin/env bash
# run.sh — Lua Preview 启动脚本
#
# 用法:
#   ./run.sh                                 启动预览器（前台），默认 game-root=../../BaiSiYeShou
#   ./run.sh --game-root /path/to/game       指定主仓库位置
#   ./run.sh --scene home                    启动后跳到指定场景
#   ./run.sh -s                              停止后台进程（仅当用 --bg 启动时）
#   ./run.sh --bg                            后台启动（写 PID 文件）
#   ./run.sh --status                        查看进程状态
#
# 其余参数会原样透传给 run.py
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
PID_DIR="$ROOT/.run"
mkdir -p "$PID_DIR"
PID_FILE="$PID_DIR/preview.pid"
LOG_FILE="$PID_DIR/preview.log"
VENV="$ROOT/.venv"

cmd_stop() {
  if [[ -f "$PID_FILE" ]]; then
    local pid; pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.5
      kill -9 "$pid" 2>/dev/null || true
      echo "[stop] preview (pid=$pid)"
    fi
    rm -f "$PID_FILE"
  fi
}

cmd_status() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "preview: running (pid=$(cat "$PID_FILE"))"
  else
    echo "preview: stopped"
  fi
}

ensure_venv() {
  if [[ ! -d "$VENV" ]]; then
    echo "[run] creating venv..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r requirements.txt
  fi
}

# ---- 参数解析 ----
GAME_ROOT_ARG=""
ACTION="start"
BG=0
PASSTHROUGH=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--stop)    ACTION="stop"; shift ;;
    --status)     ACTION="status"; shift ;;
    --bg)         BG=1; shift ;;
    --game-root)  GAME_ROOT_ARG="$2"; shift 2 ;;
    -h|--help)    sed -n '2,13p' "$0"; exit 0 ;;
    *)            PASSTHROUGH+=("$1"); shift ;;
  esac
done

if [[ "$ACTION" == "stop" ]]; then cmd_stop; exit 0; fi
if [[ "$ACTION" == "status" ]]; then cmd_status; exit 0; fi

DEFAULT_ROOT="$(cd "$ROOT/../../BaiSiYeShou" 2>/dev/null && pwd || echo "")"
GAME_ROOT="${GAME_ROOT_ARG:-$DEFAULT_ROOT}"
if [[ -z "$GAME_ROOT" || ! -d "$GAME_ROOT/scripts" ]]; then
  echo "ERROR: game root not found: '$GAME_ROOT'" >&2
  echo "       use --game-root <path> to specify" >&2
  exit 1
fi
GAME_ROOT="$(cd "$GAME_ROOT" && pwd)"

ensure_venv
echo "[run] GAME_ROOT=$GAME_ROOT"

if [[ "$BG" == "1" ]]; then
  cmd_stop
  nohup "$VENV/bin/python" run.py --game-root "$GAME_ROOT" "${PASSTHROUGH[@]}" \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[run] preview pid=$(cat "$PID_FILE") log=$LOG_FILE"
  echo "[run] stop with: ./run.sh -s"
else
  exec "$VENV/bin/python" run.py --game-root "$GAME_ROOT" "${PASSTHROUGH[@]}"
fi
