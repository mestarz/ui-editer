# nanovg_service

> 把一段 Lua 代码渲染成 PNG 的 HTTP 服务 + 浏览器端 Lua 用例管理工具。
>
> Lua 接口与 [`docs/nanovg-api.md`](../../BaiSiYeShou/docs/nanovg-api.md) 一致（与 NanoVG C API 函数签名 1:1），渲染管线为 **OSMesa 软件 OpenGL + 上游 nanovg**，最贴近 TapTap 真机的绘制行为。

## 特性

- `POST /api/render` —— 传入 Lua 字符串 + 画布尺寸，返回 PNG
- 浏览器端用 Monaco 编辑器写 Lua、左侧管理用例、右侧实时预览
- 用例以 `cases/<id>.lua` + `cases/<id>.json` 落盘，git 友好
- 几乎零系统依赖：只需 `libosmesa6-dev`；nanovg / Lua 5.4 / stb 全部 vendor

## 依赖

```bash
sudo apt install -y libosmesa6-dev build-essential cmake pkg-config
```

Node 18+。

## 启动

```bash
./run.sh                   # 自动 build C 渲染器 + npm install + 起 express+vite
./run.sh --rebuild         # 强制重新 cmake 构建 C
./run.sh -s                # 停止
./run.sh --status          # 查看
```

打开 <http://localhost:5174/>。

## 仅 HTTP 用法（不开浏览器）

```bash
curl -X POST http://localhost:3002/api/render \
  -H 'Content-Type: application/json' \
  -d '{"lua":"nvgBeginPath(vg) nvgCircle(vg,128,128,80) nvgFillColor(vg,nvgRGB(255,0,0)) nvgFill(vg)","width":256,"height":256}' \
  --output out.png
```

## CLI 直跑（无服务）

```bash
echo 'nvgBeginPath(vg) nvgRect(vg,10,10,200,200) nvgFillColor(vg,nvgRGBA(0,200,0,255)) nvgFill(vg)' \
  | renderer/build/nvg_renderer --width 256 --height 256 --font fonts/DejaVuSans.ttf > out.png
```

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST`   | `/api/render`      | body=`{lua, width=512, height=512, dpr=1}` → `image/png` |
| `GET`    | `/api/cases`       | 列出所有用例（`{id, name, width, height, updatedAt, ...}`） |
| `GET`    | `/api/cases/:id`   | 读取用例（含 `lua` 字段） |
| `POST`   | `/api/cases`       | 新建：`{name, lua, width, height, dpr, tags?}` |
| `PUT`    | `/api/cases/:id`   | 更新（任意子集） |
| `DELETE` | `/api/cases/:id`   | 删除 |

渲染失败时返回 `422` + `{error, stderr}`。

## Lua 运行环境

每次 `/api/render` 调用流程：

1. 创建独立 Lua 5.4 state，`luaL_openlibs` 启用标准库
2. 注入全局：
   - `vg` — `NVGcontext` 句柄（lightuserdata），可显式传入或由绑定层自动取（你的所有 `nvg*(vg, ...)` 调用都正确）
   - `WIDTH`、`HEIGHT`、`DPR`、`ASSETS_DIR`
   - 所有 `nvg*` 函数 + `NVG_*` 常量
3. 由宿主 `nvgBeginFrame`，执行用户脚本，若定义了 `function draw(vg, w, h)` 则再调用一次，最后 `nvgEndFrame`
4. `glReadPixels` → `stb_image_write` → PNG → stdout

### 已支持 API

完整覆盖 `docs/nanovg-api.md` 中下列章节（与 nanovg 上游一致部分）：

帧/状态、变换、颜色、路径、形状图元、填充与描边样式、渐变与图案、裁剪、文本（含字体加载/对齐/度量）、图片、混合模式、所有 `NVG_*` 枚举、`nvgDegToRad/RadToDeg`。

### 仅 TapTap 私有的扩展（被注册为 no-op，不会报错）

`nvgCreate`、`nvgDelete`、`nvgSetBloomEnabled`、`nvgSetColorSpace`、`nvgSetRenderTarget`、`nvgSetRenderOrder`、`nvgImagePatternTinted`、`nvgCreateVideo`、`nvgDeleteVideo`、`nvgEllipseArc`、`nvgForceAutoHint`/`Get`、`nvgFontSizeMethod`/`Get`、`nvgCurrentTransform`、`nvgTransform*`（矩阵工具）。

如脚本依赖 Bloom / RenderTarget 等渲染效果，本服务不实现 —— 只能落地像素。

### 字体

启动时 `fonts/DejaVuSans.ttf` 被注册为 `"default"`，可直接 `nvgFontFace(vg, "default")` 使用。需要其他字体：放进 `fonts/`，在脚本里 `nvgCreateFont(vg, "myname", "fonts/xxx.ttf")`（路径相对工作目录或写绝对路径）。

### 图片

放进 `assets/`，脚本里 `nvgCreateImage(vg, ASSETS_DIR .. "/foo.png", 0)`。

## 目录

```
nanovg_service/
├── run.sh / build.sh
├── server/                # Express REST + 子进程渲染
├── web/                   # Vite + React + Monaco 前端
├── renderer/              # C 渲染器
│   ├── CMakeLists.txt
│   ├── src/{main,lua_nvg,png_writer}.{c,h}
│   └── third_party/{nanovg,lua,stb}
├── cases/                 # 用例 .lua + .json（git 跟踪）
├── assets/                # 用户图片资源
└── fonts/DejaVuSans.ttf   # 默认字体
```

## 端口

- Express: `3002`
- Vite: `5174`

避开了 `web_layout` 占用的 `3001` / `5173`。两者可同时运行。

## MCP 集成（给 AI 用）

提供 stdio 模式的 MCP server，可在 Claude Code / Copilot CLI / Cursor 等 AI 客户端里直接挂为 tool，AI 写完一段 Lua 就能立刻看到渲染结果。

**暴露的 tools**：

| 工具 | 说明 |
|------|------|
| `nvg_render` | 输入 lua + 尺寸 (+ 可选 `time`)，返回 PNG（base64 内嵌响应里，AI 可直接看图）。Lua 脚本可读全局 `T`（秒）做时变效果 |
| `nvg_lint` | 用 4×4 微画布跑一遍脚本，只报 syntax / runtime / API 错误，不返图。比 render 快很多，适合 AI 改完代码做自检 |
| `nvg_render_animation` | 同一脚本按 `frames` × `fps` 渲染多帧，每帧的全局 `T` 不同，返回多个 image content。看动画/过渡很方便 |
| `nvg_diff` | 渲染两段 lua，返回像素差异图（红色=不同；灰=A 的 dim）+ 统计 (`changedPixels` / `changedRatio` / `maxDelta` / `meanDelta`)。视觉回归测试用 |
| `nvg_list_cases`  | 列出全部已存用例 |
| `nvg_get_case`    | 读取单个用例（含 lua 源码） |
| `nvg_save_case`   | 保存/更新用例（不传 id 则新建） |
| `nvg_delete_case` | 删除用例 |
| `nvg_api_docs` | 查 TapTap NanoVG Lua API 参考。无参=列章节；`section=...`=取整节；`query=...`=跨节模糊搜（找函数签名/常量名最快）。文档源自 `BaiSiYeShou/docs/nanovg-api.md`，可用 `NVG_API_DOCS` 环境变量覆盖路径 |

渲染失败时返回 `isError: true` + `[string "user"]:N:` 行号信息，AI 可据此修代码后重试。

**前提**：先 `./build.sh` 把 C 渲染器编译出来。MCP server 不需要 Express 服务运行，自包含。

**配置示例**（Claude Code / Cursor 的 `.mcp.json` 或对应配置文件）：

```json
{
  "mcpServers": {
    "nanovg": {
      "command": "node",
      "args": ["/abs/path/to/ui-editer/nanovg_service/mcp/server.js"]
    }
  }
}
```

可选环境变量覆盖默认路径：
- `NVG_BIN` — 渲染器二进制路径
- `NVG_CASES` — 用例目录
- `NVG_ASSETS` — 图片资源目录
- `NVG_FONT` — 默认字体 ttf
- `NVG_API_DOCS` — `nvg_api_docs` 工具读取的 markdown 路径（默认 `/root/workspace/game/BaiSiYeShou/docs/nanovg-api.md`）

**手动测试**（看 server 是否能响应）：
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"x","version":"1"}}}' \
  | node mcp/server.js
```

## 限制

- 单帧渲染，不跑 Update/Input
- TapTap 引擎私有扩展为 no-op
- 渲染器子进程默认 10s 超时
