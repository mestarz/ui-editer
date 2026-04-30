# Lua Preview (P1)

PC 上跑 BaiSiYeShou `scripts/main.lua` 的预览器。零 TapTap 依赖，开发阶段所见即所得。

## 安装

```bash
cd ui-editer/lua_preview
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 渲染走真实 nanovg + headless OpenGL（与 TapTap 真机渲染一致），按系统二选一构建：
# (a) Debian/Ubuntu/WSL：经典 OSMesa 后端
sudo apt install -y libosmesa6-dev
(cd librender && ./build.sh)
# (b) Arch / Fedora / Mesa 26+：EGL 后端（mesa 已不再打包 OSMesa）
sudo pacman -S --needed mesa            # Arch；提供 libEGL/libGL
(cd librender_egl && ./build.sh)
```

> 两个子项目产物都叫 `libnvgrender.so`，ABI 完全一致。`engine_shim/nvg.py` 会优先加载 `librender_egl/build/libnvgrender.so`，找不到再回退到 `librender/build/libnvgrender.so`，所以两个目录里只要有一个被构建过即可；也可以用 `LUA_PREVIEW_LIBRENDER=/path/to/libnvgrender.so` 显式指定。
>
> librender_egl 通过 EGL device-platform 或 `EGL_PLATFORM_SURFACELESS_MESA` 打开**与宿主进程隔离**的 EGL display，再用 FBO+`glReadPixels` 把像素回读给 Python，避免与 SDL2/pygame 自己的 EGL state 互踢。


> 注：必须用 **pygame-ce**（已在 requirements.txt 中），原版 pygame 在 Python 3.14 上有 font 模块循环导入 bug。
>
> librender 源码在 `librender/`（OSMesa 后端，Debian/WSL）和 `librender_egl/`（EGL 后端，Arch/Mesa 26+）；两者共享 `librender/third_party/{nanovg,stb}` 上游源码，无外部 git 子模块。
>
> 中文字体：`assets/fonts/MiSans-Regular.ttf` 已随项目分发（小米开源字体，~7.6MB）。当 BaiSiYeShou 工程没有 `Fonts/MiSans-Regular.ttf` 时自动回退到这份，确保 CJK 不显示成方块。
>
> 符号 / Emoji 回退链（自动注册到 native 后端的 "sans" 字体）：
> - `assets/fonts/NotoSansSymbols2-Regular.ttf` — 覆盖 ★⚙⚠✕✓⚔❤ 等符号（~672KB，OFL）
> - `assets/fonts/OpenMoji-Black.ttf` — 单色 Emoji，覆盖 👥📦🎒 等图形（~1.4MB，CC BY-SA 4.0）。注：nanovg 用的 stb_truetype 不支持彩色 emoji，故只能用单色字形版。

## 运行

```bash
./run.sh                                  # 默认 --game-root ../../BaiSiYeShou
./run.sh --game-root /path/to/BaiSiYeShou # 指定其他位置
./run.sh --scene home                     # 启动后跳到家园
./run.sh -s                               # 关闭后台进程
```

也可以直接用 venv 调 run.py：

```bash
./.venv/bin/python run.py --no-reload
./.venv/bin/python run.py --snapshot x.png --snapshot-frames 30
```

## 操作

| 键 | 行为 |
|---|---|
| **F1** | 切换调试叠层（FPS / 当前场景 / 场景目录） |
| 叠层菜单点击 | 跳到对应场景 |
| **Esc** | 退出 |

## 热重载

默认开启。每秒轮询 `scripts/**/*.lua` 的 mtime，变更则清 `package.loaded` → 重跑 `Start()` → 回到当前场景。

## 边界（不支持）

- 物理 / 真实粒子 / 视频
- 真实 SFX（已 stub 为 no-op）
- nvg 渐变（取中点纯色填充）
- 复杂 2D 变换（仅平移 + 均匀缩放）

UI、场景渲染、字体、图片、输入、事件、AssetLoader 全部 1:1。

## 故障排查（Troubleshooting）

### 启动报 `libnvgrender.so not found`
两个后端都没构建。按上面"安装"二选一构建即可。也可以通过环境变量直接指定：
```bash
LUA_PREVIEW_LIBRENDER=/abs/path/to/libnvgrender.so ./run.sh
```

### Arch / Wayland + NVIDIA：`X_GLXCreateContext BadValue`
SDL 默认走 X11/GLX，遇到 NVIDIA 私有驱动会失败。`run.sh` 在原生 Linux 上检测到 `WAYLAND_DISPLAY` 会自动切 `SDL_VIDEODRIVER=wayland`；如被覆盖可手动：
```bash
SDL_VIDEODRIVER=wayland ./run.sh
# 或退到软件渲染窗口
SDL_VIDEODRIVER=x11 SDL_VIDEO_X11_FORCE_EGL=1 ./run.sh
```

### Arch：窗口黑屏 / 标题画面像素错乱
通常意味着 `librender_egl` 抢走了 SDL 自己的 EGL current context、或者纹理上传到了错误的 GL context。请确认用的是最新版（`begin/end_frame`、`create/update/delete_image` 等入口都做了 EGL state save/restore）：
```bash
cd librender_egl && rm -rf build && ./build.sh
```

### 想强制走某一后端
```bash
LUA_PREVIEW_LIBRENDER=$PWD/librender/build/libnvgrender.so      ./run.sh   # 强制 OSMesa
LUA_PREVIEW_LIBRENDER=$PWD/librender_egl/build/libnvgrender.so  ./run.sh   # 强制 EGL
```

### 离屏快照（无需任何窗口/显示）
```bash
SDL_VIDEODRIVER=dummy ./.venv/bin/python run.py --snapshot out.png --snapshot-frames 30
```

### libEGL warnings：`pci id for fd N: …, driver (null)` / `failed to create dri2 screen`
NVIDIA 私有驱动没装 EGL 部分时 Mesa 26 会先尝试 GBM/DRI2 失败再退到 llvmpipe。是噪音，不影响渲染（最终软件路径成功）。要消音可装 NVIDIA EGL 包（如 Arch 的 `nvidia-utils` 提供 `libnvidia-egl-*`）。
