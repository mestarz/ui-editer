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
#
# ── 窗口缩放配置 ──────────────────────────────────────
# WINDOW_SCALE: 物理窗口相对于 1280x720 设计画布的放大倍数。
#   "auto"   根据屏幕宽度自动选择：≥3840(4K)→2.0  ≥2560(QHD)→1.5  其余→1.0
#   数字     如 "1.0" "1.5" "2.0"，固定使用该倍数
WINDOW_SCALE="1.0"
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
        local pid
        pid="$(cat "$PID_FILE")"
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

# ---- 分辨率检测 ----
detect_screen_width() {
    if command -v xrandr &>/dev/null; then
        xrandr 2>/dev/null | awk '/^Screen 0/{print $8; exit}'
    fi
}

resolve_window_scale() {
    local setting="$1"
    if [[ "$setting" == "auto" ]]; then
        local w
        w=$(detect_screen_width)
        if [[ "${w:-0}" -ge 3840 ]]; then
            echo "2.0"
        elif [[ "${w:-0}" -ge 2560 ]]; then
            echo "1.5"
        else
            echo "1.0"
        fi
    else
        echo "$setting"
    fi
}

# ---- 参数解析 ----
GAME_ROOT_ARG=""
ACTION="start"
BG=0
PASSTHROUGH=()
while [[ $# -gt 0 ]]; do
    case "$1" in
    -s | --stop)
        ACTION="stop"
        shift
        ;;
    --status)
        ACTION="status"
        shift
        ;;
    --bg)
        BG=1
        shift
        ;;
    --game-root)
        GAME_ROOT_ARG="$2"
        shift 2
        ;;
    -h | --help)
        sed -n '2,13p' "$0"
        exit 0
        ;;
    *)
        PASSTHROUGH+=("$1")
        shift
        ;;
    esac
done

if [[ "$ACTION" == "stop" ]]; then
    cmd_stop
    exit 0
fi
if [[ "$ACTION" == "status" ]]; then
    cmd_status
    exit 0
fi

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

RESOLVED_SCALE=$(resolve_window_scale "$WINDOW_SCALE")
echo "[run] WINDOW_SCALE=$RESOLVED_SCALE (config='$WINDOW_SCALE')"

# ---- SDL / GL 兼容性环境（用户已显式设置则保持原值） ----
# 仅对原生 Linux（Arch/Fedora/Ubuntu 等）介入；WSL/WSLg 走它默认的 X11+GLX
# 路径，因为 OSMesa 后端不会与 SDL 的 GL state 冲突，无需特殊化。
_is_wsl=0
if [[ -n "${WSL_DISTRO_NAME:-}" ]] || grep -qiE '(microsoft|wsl)' /proc/sys/kernel/osrelease 2>/dev/null; then
    _is_wsl=1
fi
if [[ "$_is_wsl" == "0" ]]; then
    if [[ -z "${SDL_VIDEODRIVER:-}" ]]; then
        if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
            # Wayland 桌面：直接走 wayland driver，绕开 X11/GLX 整条路
            # （Arch + NVIDIA 上 SDL 走 X11/GLX 会报 X_GLXCreateContext BadValue）
            export SDL_VIDEODRIVER=wayland
        elif [[ -z "${DISPLAY:-}" ]]; then
            # 没显示（CI / 纯快照）退到 dummy 驱动
            export SDL_VIDEODRIVER=dummy
        fi
    fi
    # X11 路径下让 SDL 用 EGL 而非 GLX
    export SDL_VIDEO_X11_FORCE_EGL="${SDL_VIDEO_X11_FORCE_EGL:-1}"
fi
echo "[run] WSL=$_is_wsl  SDL_VIDEODRIVER=${SDL_VIDEODRIVER:-<auto>}  SDL_VIDEO_X11_FORCE_EGL=${SDL_VIDEO_X11_FORCE_EGL:-<auto>}"

if [[ "$BG" == "1" ]]; then
    cmd_stop
    nohup "$VENV/bin/python" run.py --game-root "$GAME_ROOT" --window-scale "$RESOLVED_SCALE" "${PASSTHROUGH[@]}" \
        >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "[run] preview pid=$(cat "$PID_FILE") log=$LOG_FILE"
    echo "[run] stop with: ./run.sh -s"
else
    exec "$VENV/bin/python" run.py --game-root "$GAME_ROOT" --window-scale "$RESOLVED_SCALE" "${PASSTHROUGH[@]}"
fi
