# ui-editer

> 给 [BaiSiYeShou](https://github.com/mestarz/BaiSiYeShou) 配套的 UI 迭代加速工具集。
> 两个**互相独立**的子项目，都以 `--game-root` 指向主仓库，**只读消费**，不写回源码。

## 子项目

| 目录 | 说明 | 技术栈 |
|---|---|---|
| [`lua_preview/`](./lua_preview) | PC 端运行真实 Lua 的所见即所得预览器 | Python + lupa + pygame |
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

# 3. 指定游戏根目录（任意路径）
./run.sh --game-root /opt/games/BaiSiYeShou

# 4. 关闭服务
./run.sh -s
```

## 共同约定

- `--game-root <path>`：指向 BaiSiYeShou 仓库根目录。默认 `../../BaiSiYeShou`。
- 两个项目**绝不**修改主仓库源码。所有产出在各自 `exports/` 或剪贴板。
- 共享真相源 `scripts/scenes/Registry.lua`，自动列出所有可注册场景。

## 目录结构

```
ui-editer/
├── README.md
├── .gitignore
├── lua_preview/
│   ├── run.sh            # 启动 / -s 关闭
│   ├── run.py
│   ├── requirements.txt
│   ├── engine_shim/      # 伪 TapTap 引擎实现
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
- 两子项目不共享代码
