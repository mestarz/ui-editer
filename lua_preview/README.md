# Lua Preview (P1)

PC 上跑 BaiSiYeShou `scripts/main.lua` 的预览器。零 TapTap 依赖，开发阶段所见即所得。

## 安装

```bash
cd ui-editer/lua_preview
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 渲染走真实 nanovg + OSMesa（与 TapTap 真机渲染一致），需要构建一次 librender.so：
sudo apt install -y libosmesa6-dev
(cd librender && ./build.sh)
```

> 注：必须用 **pygame-ce**（已在 requirements.txt 中），原版 pygame 在 Python 3.14 上有 font 模块循环导入 bug。
>
> librender 源码在 `librender/`，依赖只有 OSMesa；vendored 了 nanovg/stb 上游源码，无外部 git 子模块。
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
