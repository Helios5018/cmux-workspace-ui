<div align="center">

# cmux-workspace-ui

macOS cmux 的自定义侧栏：一栏看全 workspace、AI 用量和 tmux 会话。

*A custom cmux sidebar for workspaces, AI usage meters and tmux sessions — built on cmux-sentinel.*

![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Sidebar](https://img.shields.io/badge/sidebar-cmux%20JS-F7DF1E)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

## 简介

[cmux](https://github.com/manaflow-ai/cmux) 支持用 JavaScript 编写自定义侧栏。本项目提供一个 `workspaces` 侧栏，把三类信息放进一列：

- **USAGE**：Claude Code、GPT/Codex、Grok、OpenCode Go 的已用额度和重置倒计时；
- **WORKSPACES**：cmux workspace 列表，包括 Agent 工作状态、分支和未读数；
- **TMUX**：本机 tmux 会话，以及会话上的备注、项目、生命周期和端口标注。

侧栏只负责展示和轻量交互。采集额度、同步 tmux 元数据、执行关闭等动作，都交给后台的 Python worker 和本机 URL 处理器。

### 与上游 cmux-sentinel 的关系

本仓库 fork 自 Oliver Kriska 的 [cmux-sentinel](https://github.com/oliver-kriska/cmux-sentinel)（MIT），保留了完整的上游 Git 历史。在此基础上新增了 JS 侧栏、tmux 会话管理，以及 Grok、OpenCode Go、多 cmux 实例等本地扩展，并把它们设为默认安装模式。

| 名称 | 含义 |
| --- | --- |
| `cmux-workspace-ui` | 本仓库名，也就是这个 fork |
| `cmux-sentinel` | 沿用上游的命令名、URL scheme（`cmux-sentinel://`）、配置和状态目录名 |
| local profile | 默认安装模式：JS 侧栏 + tmux worker（本仓库的扩展） |
| upstream profile | 上游原版：Swift 侧栏 + launchd 采集器，需要显式选择 |

所以安装后执行的命令仍是 `~/bin/cmux-sentinel`，配置仍在 `~/.config/cmux-sentinel/`。

## 侧栏能展示什么

### 顶栏

分别统计需要你处理、正在工作、正在压缩上下文的 workspace 数量。

### USAGE

| 提供方 | 侧栏标签 | 展示的窗口 |
| --- | --- | --- |
| Claude Code | `5h` / `7d`，可选 `m7d`、`spend` | session、week；可选的模型周额度和额外消费 |
| GPT / Codex | `cx5h` / `cx7d` | session、week |
| Grok | `grokcredits` | week |
| OpenCode Go | `go5h` / `go7d` / `go1m` | session、week、month |

百分比均表示**已用量**。数据超过 900 秒未更新时显示 `stale`；出错时显示简短状态（如 `⚠ sign in`、`⚠ offline`、`⚠ rate limited`），鼠标悬停可查看完整原因。

### WORKSPACES

- `⌘1…⌘9` 快捷键提示，编号规则与 cmux 一致（分组标题和折叠分组的成员不占编号）；
- 状态行：`Working…`（多个 Agent 时显示 `×N`）、`Compacting…`、`asking…`、`needs you`、`idle`；
- 分支、PR 和未提交改动标记，以及未读数、置顶标记和分组名；
- 支持拖拽排序；右键菜单可置顶、设置或清除颜色（Orange / Blue / Green / Red）、上移、下移、移到顶部、关闭。

### TMUX

点击会话展开详情，可以看到：

- 会话级 tmux 选项 `@note`、`@project`、`@lifecycle`、`@port`，以及窗口数和连接数；
- `@port` 中每个 1–65535 的纯数字端口都会显示为一个链接，点击后在默认浏览器打开 `http://127.0.0.1:<port>`，其他文本照原样显示；
- 「× 关闭会话」按钮。`@lifecycle` 为 `persistent`（或备注里含「常驻」「长驻」）的会话，需要二次确认才会关闭。

三个模块都可以点击标题折叠，也可以右键调整顺序，布局会持久保存。

## 快速开始

### 依赖

- macOS，以及支持 JS 自定义侧栏的 cmux（当前实现基于 cmux 0.64.24）
- Python 3.9+（只用标准库，无第三方包）、tmux、jq
- 所启用提供方的 CLI 和登录状态：Codex CLI、Grok CLI（`grok login`），可选 Claude Code 和 Pi（OpenCode Go）
- 开发测试另需 Node.js、shellcheck、markdownlint

### 安装与启动

```sh
git clone https://github.com/Helios5018/cmux-workspace-ui.git
cd cmux-workspace-ui
./install.sh
~/bin/cmux-sentinel start
```

`./install.sh` 默认使用 local profile，会完成以下几步：

- 把 `workspaces.js` 和 Python 模块复制到用户目录；
- 注册 `cmux-sentinel://` URL 处理器；
- 为已启用的提供方创建额度 workspace。

安装器**不会**启动 worker，也不会安装 LaunchAgent、改动登录凭据。首次安装默认启用 `codex grok`，已有配置会保留。

`start` 会创建或复用名为 `cmux-sentinel-refresh` 的 tmux session，在里面运行两个 worker：用量每 300 秒刷新一次，tmux 元数据每 5 秒同步一次。整个过程不监听任何 TCP 端口。之后在 cmux 中启用侧栏：

```sh
cmux sidebar validate workspaces
cmux sidebar reload workspaces
cmux sidebar select workspaces
```

只想准备文件、不注册处理器也不创建 workspace（例如离线检查）时，可以运行 `./install.sh --no-setup --no-actions`。

### 常用命令

```sh
~/bin/cmux-sentinel doctor    # 只读健康检查，不发网络请求
~/bin/cmux-sentinel usage     # 打印已启用提供方的用量
~/bin/cmux-sentinel refresh   # 立即刷新一次用量
```

升级流程是：在仓库里合并改动，运行 `make check` 和 `./install.sh`。已经在运行的 worker 不会自动换成新代码，需要先 `tmux kill-session -t cmux-sentinel-refresh`，再执行 `start`。详见[运维说明](docs/operations.md)。

## 配置

主配置文件是 `~/.config/cmux/usage-sentinels.env`。Python 端只读取其中的普通赋值，不执行 shell 代码。

| 配置项 | 默认值 / 用途 |
| --- | --- |
| `USAGE_PROVIDERS` | `codex grok`；可选值为 `claude`、`codex`、`grok`、`opencode-go` |
| `SENTINEL_REFRESH_TMUX` | worker 所在的 tmux session，默认 `cmux-sentinel-refresh` |
| `CMUX_EXTRA_SOCKETS` | 额外的 cmux socket（空格分隔），可同时向多个 cmux 实例写入 |
| `SENTINEL_CMUX_BIN` / `SENTINEL_TMUX_BIN` | 显式指定 `cmux` / `tmux` 路径，默认从 PATH 查找 |
| `CMUX_SENTINEL_STATE_DIR` | 状态目录，默认 `~/.local/state/cmux-sentinel` |
| `SENTINEL_OPENCODE_GO_AUTH_FILE` | 指定 OpenCode Go 凭据文件路径（默认读取 Pi 的 `auth.json`） |

启用 `claude` 或 `opencode-go` 时，先把它加入 `USAGE_PROVIDERS`，再运行 `~/bin/cmux-sentinel setup`，然后手动重启用量 worker。各提供方的鉴权方式和错误处理见[运维说明](docs/operations.md)和[架构说明](docs/architecture.md)。

## 架构

```text
提供方凭据 (Keychain / CLI auth)            tmux server
      │                                        │
      ▼                                        ▼
 refresh.py + 各提供方采集器               tmux_sidebar.py
 （每 300 秒）                              （每 5 秒）
      │                                        │
      └──── title / progress ────┐  ┌─ description (sidebar_metadata.py, 加锁)
                                 ▼  ▼
                           cmux workspace 数据
                                 │
                                 ▼
                       sidebars/workspaces.js ── 点击端口 ──▶ 默认浏览器
                                 │
                       cmux-sentinel:// 签名链接
                                 ▼
             macOS URL App → action_handler.py → tmux_actions.py
```

- **JS 侧栏**（`sidebars/workspaces.js`）读取 cmux 提供的 workspace、分组和时钟数据。额度来自额度 workspace 的 title 和 progress，tmux 快照来自 description 中的 `sentinel-tmux:` JSON。它不启动进程，也不重写自身。
- **Python worker**（`src/`）向 cmux 写入数据。额度 workspace 按 title 标签识别，不保存位置型 ref；description 的读写统一走 `sidebar_metadata.py`，并用文件锁避免并发覆盖。
- **动作链路**：关闭会话、保存布局等动作通过 `cmux-sentinel://` 链接交给注册的 URL App 处理。关闭动作会校验 HMAC 签名，以及 socket、server PID、session ID、创建时间；执行前还会重新读取最新的常驻标注。会话名和备注只作为数据使用，不会被当作命令执行。

模块职责、数据格式和兼容边界见[架构说明](docs/architecture.md)。

## 隐私与安全

- 凭据保留在各提供方自己的存储里（Claude Code 的 Keychain、Codex / Grok CLI、Pi 的 `auth.json`），不会被复制到本项目的源码、日志、侧栏或命令参数中。Claude 请求头通过 stdin 传给 curl。
- Codex 的鉴权和刷新由 Codex app server 负责，Grok、Claude Code 的登录刷新也都由各自的 CLI 管理。
- 只查询用量接口，不调用模型。
- 状态文件和签名密钥位于状态目录，权限为 `0600`。URL App 不监听网络，动作异常会追加写入 `url-action-errors.log`。
- `make secrets` 会检查已跟踪文件，防止真实 UUID、用户主目录绝对路径或 token 被提交。

## 项目结构

```text
sidebars/   JS 侧栏（默认）与 Swift 兼容实现
src/        Python worker、采集器、配置、元数据写入与 URL 动作
bin/        cmux-sentinel 入口与上游 shell 采集器、doctor、setup
hooks/      上游 Agent 状态 hooks（Claude / Amp / Zed）
scripts/    安装器、URL App 注册、秘密检查、发布脚本
tests/      Python、JS、shell 测试与本机运行时验证
docs/       运维、架构、上游兼容说明及配置模板
```

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [docs/operations.md](docs/operations.md) | 安装合同、配置与路径、日常检查、升级、回退 |
| [docs/architecture.md](docs/architecture.md) | 模块边界、状态与数据格式、各提供方的协议 |
| [docs/upstream.md](docs/upstream.md) | upstream profile、Zed 集成、发布流程 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 修改位置、检查命令、上游合并注意事项 |
| [AGENTS.md](AGENTS.md) | 项目约束与 Agent 阅读路由 |
| [CHANGELOG.md](CHANGELOG.md) | 版本记录（沿用上游） |

## 开发与验证

```sh
make test-local   # Python 隔离测试 + JS 逻辑测试，不需要账号和真实 tmux/cmux
make ci           # shellcheck、秘密检查、Markdown、打包检查、语法检查、全部离线测试（可在 Linux 运行）
make check        # make ci + 已安装 cmux 的 JS 运行时交互测试 + 仓库侧栏解释验证（需 macOS/cmux）
```

其他目标：

- `make test-upstream`：上游 shell 回归测试；
- `make sidebar-live`：临时挂载侧栏，供人工目视检查；
- `make amp-live`：调用本机 Amp CLI 做真实验证；
- `make doctor`：上游的只读健康检查。

如果 cmux 运行时不在标准位置，可以用 `CMUX_SIDEBAR_RUNTIME` 指定 `SidebarRuntime.js` 的路径。注意，便携逻辑测试和解释验证通过，都不等于像素渲染正确，UI 改动仍需要目视检查。

## 上游兼容

- 上游的 shell 采集器、hooks、Swift 侧栏和发布设施都保留着。需要原版行为时运行 `./install.sh --profile upstream`，它会安装 LaunchAgent 模板，并支持 Claude、Codex、Amp 采集和 Zed 集成。上游命令通过 `CMUX_SENTINEL_PROFILE=upstream` 选择。
- cmux 加载同名侧栏时，JS 优先于 Swift。从 local 切回 Swift 之前，要先移走已安装的 `workspaces.js`。
- local 模式下 `cmux-sentinel update` 会拒绝执行，以免远程上游覆盖本地扩展。上游改动应在本仓库合并并验证后，再重新安装。
- `VERSION`、`CHANGELOG.md` 和 Homebrew 配方仍对应上游 v0.2.3，本仓库的扩展没有另行发布。

## 当前边界

- 只支持 macOS，依赖 cmux 的 JS 侧栏能力；部分 Swift 维护经验来自 cmux 0.64.20–0.64.24。
- OpenCode Go 只在 JS 侧栏展示。Swift 兼容侧栏不保证与 JS 版功能一致，例如端口只显示为文本。
- 没有 workspace 的 cmux 窗口无法接收 tmux 数据，因为数据需要写入某个 workspace 的 description。

## 相关项目

- [Helios5018/cmux](https://github.com/Helios5018/cmux)：基于上游 manaflow-ai/cmux 的个人 fork（macOS 终端 / Agent 工作台）
- [Helios5018/cmux-agent-remote](https://github.com/Helios5018/cmux-agent-remote)：在浏览器或手机上远程查看和控制 cmux 里的 Agent

## 致谢

- [Oliver Kriska / cmux-sentinel](https://github.com/oliver-kriska/cmux-sentinel)：本项目的上游，提供了用量采集器、Agent 状态 hooks、Swift 侧栏和发布设施。
- [CC Switch](https://github.com/farion1231/cc-switch)：Grok 用量协议改编自其 v3.20.1 的 `subscription_grok.rs`。
- [manaflow-ai/cmux](https://github.com/manaflow-ai/cmux)：侧栏的宿主应用。

## 许可证

[MIT](LICENSE)，Copyright (c) 2026 Oliver Kriska。`src/grok_usage.py` 中的 Grok 协议改编部分另受 [CC Switch 的 MIT 许可](LICENSE-CC-Switch)（Copyright (c) 2025 Jason Young）约束。
