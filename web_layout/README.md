# Web Layout Editor

浏览器内可视化拖拽 BaiSiYeShou UI 元素，导出 JSON + Markdown 报告供 AI 改源码。
**不修改主仓库源码**，输出落在浏览器下载目录。

## 运行

```bash
cd ui-editer/web_layout
./run.sh                                  # 默认 --game-root ../../BaiSiYeShou
./run.sh --game-root /path/to/BaiSiYeShou # 指定其他位置
./run.sh -s                               # 关闭后台 Express + Vite
./build.sh                                # 前端 vite build → dist/
```

首次会自动 `npm install`。打开 http://localhost:5173/

## 架构

```
web_layout/
├── run.sh / build.sh
├── server/                    # Node 后端：fengari 跑 Lua
│   ├── index.js               # Express，端口 3001
│   ├── lua-runtime.js         # fengari 启动 + scene 切换 + JSON 序列化
│   └── recorder/boot.lua      # 引擎 stub + Renderer hook（核心录制逻辑）
├── web/                       # 浏览器前端
│   ├── index.html
│   └── src/
│       ├── main.js            # 入口：场景列表、状态、剪贴板导出 + 富 Markdown
│       ├── editor.js          # Canvas 元素渲染 + 拖拽 / 缩放 / 多选 + UI 树
│       └── style.css
└── vite.config.js             # /api → :3001 代理
```

## 工作流

1. 启动服务 → fengari 自动加载 `<game-root>/scripts/main.lua`
2. 左侧选场景 → 调 `/api/record/<id>` → boot.lua 切场景，hook 后的 Renderer.* 与 nvgImagePattern 把每次绘制 push 进 `__recorder.events`
3. 浏览器拿到事件列表，在 1280×720 canvas 中给每个元素画一个可拖矩形；右侧按 src 文件分组展示 UI 树
4. 拖完点 "📋 复制 overrides+report 到剪贴板"，AI 拿到的 Markdown 包含：
   - 修改前后矩形 + 偏移量
   - 该行 ±10 行源码上下文（目标行 `>>>` 标注）
   - 完整调用栈（最多 8 层 file:line）
   - 父帧上下文（调用栈第 2 层 ±6 行）
   - 同区域兄弟元素（±100px，仅参考不要动）

## API

- `GET /api/scenes` → `{ scenes: [{id, module, phase}, ...] }`
- `GET /api/record/:id` → `{ scene, events: [{id, type, api, x, y, w, h, depth, src, hint, align, stack}, ...] }`
- `POST /api/reload` → 重置 fengari Lua 状态并重 boot
- `GET /api/source?file=&line=&ctx=` → `{ file, line, lines: [{n,t}] }`（白名单 `scripts/` 下文件）

## 操作

- 单击：选中
- Shift + 单击：加入/移出多选
- 拖动元素：移动（多选时整体平移）
- 拖角/边把手：8 向缩放
- Esc：取消选择
- R：重置选中元素
- 右侧树：搜索 / "仅显示已修改" / 点击同步选中
- 🔄 重载 Lua：源码变更后无需重启服务
- 修改保存在浏览器 localStorage，刷新不丢失

## 与项目1（lua_preview）的关系

完全独立。lua_preview 跑真 Lua + pygame 像素级渲染；web_layout 只录制矩形 bbox 不做真渲染。
