# ui-editer

> 面向 **TapTap 小游戏引擎（NanoVG + Lua）** + 采用 [BaiSiYeShou](https://github.com/mestarz/BaiSiYeShou) 同款架构（`scripts/scenes/Registry.lua` 表驱动场景 + `SceneManager` / `GameFlow` 入口）的项目，配套的 UI 迭代加速工具集。
>
> 三个**互相独立**的子项目。`lua_preview` / `web_layout` 以 `--game-root` 指向目标项目根，**只读消费**；`nanovg_service` 不依赖具体项目，是通用的 Lua → NanoVG 渲染沙盒。
>
> ⚠️ 不是通用 Lua/UI 工具：依赖具体的引擎 API（`Renderer.FillRect/PixelPanel/DrawImage/...`、`nvgImagePattern` 等）与场景注册约定。要在其他项目复用，需按 [兼容清单](#兼容清单) 适配。

## 子项目

| 目录 | 说明 | 技术栈 |
|---|---|---|
| [`lua_preview/`](./lua_preview) | PC 端运行真实 Lua 的所见即所得预览器（vendored nanovg + OSMesa，与真机绘制一致） | Python + lupa + pygame + cffi + C |
| [`nanovg_service/`](./nanovg_service) | 把一段 Lua 渲染成 PNG 的 HTTP 服务 + 浏览器端 Lua 用例管理工具；附带 MCP server 让 AI 调用 | Node + Express + Vite/React + C (vendored nanovg + Lua 5.4 + OSMesa) |
| [`web_layout/`](./web_layout) | 浏览器拖拽 UI 元素，导出 overrides + Markdown 报告供 AI 改源码 | Node (fengari) + Vite |

## 快速开始

```bash
# 1. 克隆主仓库 + 工具仓库（位于同一父目录）
cd ~/workspace/games
git clone git@github.com:mestarz/BaiSiYeShou.git
git clone git@github.com:mestarz/ui-editer.git

# 2. 启动其中一个工具
cd ui-editer/lua_preview && ./run.sh                    # 默认 --game-root ../../BaiSiYeShou
cd ui-editer/web_layout && ./run.sh                     # 同上
cd ui-editer/nanovg_service && ./build.sh && ./run.sh   # 不需要 --game-root，自包含

# 3. 指定游戏根目录（任意路径，仅 lua_preview / web_layout 适用）
./run.sh --game-root /opt/games/BaiSiYeShou

# 4. 关闭服务
./run.sh -s
```

## 三个子项目怎么选

| 你想做什么 | 用哪个 |
|---|---|
| 在 PC 上跑真实游戏 Lua、所见即所得改样式 | **lua_preview** |
| 拖拽改 UI 元素、生成 overrides 给 AI 改源码 | **web_layout** |
| 写一段独立 Lua 片段，立刻看 nanovg 渲染结果（做控件原型 / 视觉回归 / AI 自检） | **nanovg_service** |

## 共同约定

- `--game-root <path>`：指向 BaiSiYeShou 仓库根目录。默认 `../../BaiSiYeShou`（仅 `lua_preview` / `web_layout` 使用，`nanovg_service` 不依赖）。
- `lua_preview` / `web_layout` **绝不**修改主仓库源码。所有产出在各自 `exports/` 或剪贴板。
- 共享真相源 `scripts/scenes/Registry.lua`，自动列出所有可注册场景。
- 三者**均 vendor 自己依赖的上游 C 库**（nanovg / Lua / stb），不共享源码，可独立编译。

## 目录结构

```
ui-editer/
├── README.md
├── .gitignore
├── lua_preview/
│   ├── run.sh            # 启动 / -s 关闭
│   ├── run.py
│   ├── requirements.txt
│   ├── librender/        # vendored nanovg + OSMesa，编为 libnvgrender.so
│   ├── engine_shim/      # 伪 TapTap 引擎实现（cffi 调 librender）
│   ├── assets/fonts/     # 自带 MiSans / NotoSansSymbols2 / OpenMoji-Black
│   └── README.md
├── nanovg_service/
│   ├── run.sh            # 启动 Express(:3002) + Vite(:5174) / -s 关闭
│   ├── build.sh          # cmake 构建 C 渲染器
│   ├── package.json
│   ├── server/           # Express REST：/api/render + /api/cases CRUD
│   ├── web/              # Vite + React + Monaco 前端
│   ├── renderer/         # C：vendored nanovg + Lua 5.4 + stb，OSMesa 离屏 GL → PNG
│   ├── mcp/              # MCP server（给 AI 当工具用）
│   ├── cases/            # Lua 用例 .lua + .json
│   └── README.md
└── web_layout/
    ├── run.sh            # 启动 / -s 关闭
    ├── build.sh          # 前端构建
    ├── package.json
    ├── server/           # Node + fengari 录制后端
    ├── web/              # Vite 前端
    └── README.md
```

## 不做的事

- 不做"AI 自动改源码"环节
- 不做手机端预览（PC only）
- web_layout 不跑 Update/Input，只跑 Draw 一帧
- nanovg_service 不实现 TapTap 私有扩展（Bloom/RenderTarget 等），只落像素
- 三个子项目不共享代码

## 兼容清单

`lua_preview` / `web_layout` 复用到其他项目时，目标项目需满足：

1. **引擎**：TapTap 小游戏（NanoVG + Lua 5.x），全局存在 `nvg*`、`graphics`、`input`、`fileSystem` 等 API
2. **入口**：`scripts/main.lua` 提供 `Start()` 函数；逐帧调用走 `SceneManager.Draw`
3. **场景注册**：`scripts/scenes/Registry.lua` 形如 `{ id = "...", module = "...", phase = "..." }` 的声明式表
4. **跨场景跳转**：通过 `GameFlow.Enter*(...)` 入口（web_layout 服务端会调用）
5. **绘制 API**：常用 `Renderer.FillRect/StrokeRect/FillRounded/PixelPanel/HPBar/DrawImage/TextLeft/TextCenter/TextRight/FillCircle/Line` —— 不在这个清单里的自定义绘制 API 需要在 `web_layout/server/recorder/boot.lua` 的 `patch_renderer` 中追加 wrap

不满足以上前提的项目，可参考本仓库实现思路自己改造，但本仓库不保证开箱即用。`nanovg_service` 不在此清单约束内 —— 它对游戏项目零依赖，任何能写 nanovg Lua 的场景都能直接用。
