# Agent Sync · 多 AI Agent 对话同步工具（网页版）

自动检测本机已安装的 AI Agent（Claude Code、Codex、WorkBuddy、OpenClaw、QClaw、Gemini 等），
持续监听它们新产生的对话，并以可读格式**双向推送**到其他选中的 Agent。

网页版把后端做成一个本地 Web 服务：浏览器打开 UI，后端进程跑在你自己的电脑上，
直接访问 `~/.claude`、`~/.codex`、`~/.workbuddy` 等真实的 Agent 数据目录。

## 一、拉取并运行（推荐，本地优先）

源码托管在 GitHub，国内可走 GitCode 镜像源下载：

```bash
# 主源：GitHub
git clone https://github.com/liuliucomputer/agent-sync.git

# 国内镜像：GitCode（需先在 GitCode 导入该 GitHub 仓库）
git clone https://gitcode.net/liuliucomputer/agent-sync.git

cd agent-sync
python server.py
# 浏览器打开 http://localhost:8080
```

- 仅依赖 Python 标准库，**无需** `pip install`
- 默认端口 8080，可用 `--port 9000` 修改；绑定 `0.0.0.0`
- 首次打开页面需要输入**访问 ID**（见下方说明）

## 二、访问 ID 验证

为保护实例，网页版带有访问闸门：

1. 后端每次启动会**随机生成一个访问 ID**，打印到控制台，并写入项目根目录的 `access_id.txt`
2. 浏览器打开页面后，在「🔑 访问验证」框中输入该 ID，验证成功才能进入
3. ID 也支持通过环境变量固定：`ACCESS_ID=AS-XXXX-XXXX python server.py`

> 这是轻量访问控制：确保使用的人确实运行了后端、拥有该实例的 ID。
> 云端演示实例没有你的本地 Agent 文件，打开后只能看到说明与「体验模拟同步」。

## 三、桌面版（可选）

`main.py` 是原生 tkinter 半透明桌面程序，`requirements.txt` 含打包依赖（`pyinstaller`、`pywin32`）：

```bash
pip install -r requirements.txt
python main.py
# 打包： pyinstaller build.spec
```

## 四、支持的 Agent

| Agent | 读取 | 写入 | 数据源 |
|-------|------|------|--------|
| Claude Code | ✅ | ✅ | `history.jsonl` + `projects/*.jsonl` |
| Codex (OpenAI) | ✅ | ✅ | `sessions/**/*.jsonl` |
| WorkBuddy | ✅(旧格式) | ✅ | `workspace/sessions/<uuid>/*.jsonl` |
| QClaw | ✅ | ✅ | `.qclaw/agents/main/agent/sessions` |
| OpenClaw | ✅(日志) | ❌ | SQLite |
| Gemini CLI | ✅ | ❌ | 目录（仅读取） |
| OpenCode / Mavis | ❌ | ❌ | 格式未知 |

> 自定义安装位置：在对应 Agent 卡片右侧文本框粘贴其配置目录的绝对路径即可（如
> `C:\Users\你的用户名\.claude`）。网页版因浏览器安全限制无法弹出文件夹选择，需手动粘贴。

## 五、工作原理

选中多个 Agent 后，后端会：
1. 读取每个选中 Agent 的新对话记录（统一为 `{role, text, ts}`）
2. 用 MD5(role+text前100字+ts) 去重
3. 把每个源 Agent 的新消息，以目标 Agent 的原生 JSONL 格式追加写入

数据全程只在本机处理，不会上传。

## 目录结构

```
agent-sync/
├── engine.py            # 检测 / 读取 / 写入 / 同步核心逻辑（零依赖）
├── server.py            # 网页版后端（Python 内置 http.server）
├── main.py              # 桌面版（tkinter）
├── web/index.html       # 前端界面（含访问闸门 + 拉取说明）
├── push_to_github.bat   # 维护者：一键推送到 GitHub（Windows）
├── push_to_github.sh    # 维护者：一键推送到 GitHub（macOS/Linux）
└── requirements.txt     # 桌面版打包依赖
```

## 六、维护者：如何把代码推送到 GitHub（离线 bundle 方式）

源码通过离线 `agent-sync.bundle` 分发。若要把最新代码推到 GitHub 上的
`liuliucomputer/agent-sync`，在**能访问 github.com** 的机器上（必要时开 VPN）：

1. 把 `agent-sync.bundle` 与 `push_to_github.bat` / `push_to_github.sh` 拷到同一目录
2. 运行对应脚本：
   - Windows：双击 `push_to_github.bat`
   - macOS/Linux：在终端执行 `bash push_to_github.sh`
3. 脚本会依次：从 bundle 还原仓库 → 检查 `gh` 登录 → 创建 `agent-sync` 公开仓库 → 推送 `master`

前提：目标机器已 `gh auth login -h github.com`（仓库已存在则自动跳过创建直接推送）。
