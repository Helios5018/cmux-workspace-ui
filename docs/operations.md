# 安装、升级与运维

## 安装合同

在项目根目录执行 `./install.sh`。local 安装器复制 JS、全部 `src/*.py`、所需 shell 工具和 CC Switch 许可，注册 `cmux-sentinel://` 处理器并创建启用的额度 workspace。新配置启用 Codex 和 Grok；已有 `usage-sentinels.env` 保持不变。

安装器不启动或停止 worker、不安装 LaunchAgent、不修改模型配置和登录凭据。修改过的目标文件先备份，最多保留最近三份。`--no-setup --no-actions` 只准备文件，适合离线检查或隔离安装测试。

完整安装后手动运行：

```sh
~/bin/cmux-sentinel start
cmux sidebar validate workspaces
cmux sidebar reload workspaces
cmux sidebar select workspaces
```

`start` 复用 `cmux-sentinel-refresh` session，分别补齐用量和 tmux 同步 worker，设置用途、项目、生命周期和端口标注。没有 TCP 监听端口。它不会重启仍存活的旧代码进程。

## 配置与路径

| 配置 | 默认值 / 用途 |
| --- | --- |
| `~/.config/cmux/usage-sentinels.env` | `USAGE_PROVIDERS="codex grok"`、`SENTINEL_REFRESH_TMUX="cmux-sentinel-refresh"` |
| `SENTINEL_CMUX_BIN`、`SENTINEL_TMUX_BIN` | 默认从 PATH 发现命令，可显式指定 |
| `CMUX_SOCKET_PATH` | 默认用户 cmux socket；由启动器传给 worker |
| `CMUX_EXTRA_SOCKETS` | 可选的额外 cmux socket，空格分隔；默认不连接额外实例 |
| `CMUX_SENTINEL_STATE_DIR` | 默认 `$XDG_STATE_HOME/cmux-sentinel`，未设置 XDG 时为 `~/.local/state/cmux-sentinel` |
| `~/.config/cmux-sentinel/local/` | 安装的 Python 模块、URL 处理器安装工具和许可 |
| `~/.config/cmux/sidebars/workspaces.js` | 当前 UI |
| `~/.local/share/cmux-sentinel/Cmux Sentinel Actions.app` | 无网络监听的本机 URL 处理器；内置 `PATH` 与 `SENTINEL_*_BIN` |
| `~/.config/cmux-sentinel/VERSION` | 上游基础版本、local profile、安装时间、commit 和包含 JS/Python 的源码指纹 |

本地 Python 配置只读取普通赋值，不执行 env 文件中的 shell 代码。Python 配置支持 `claude`、`codex`、`grok`、`opencode-go`，shell 上游 profile 的其他 provider 见上游资料。状态目录覆盖必须在 worker 和 URL App 进程中一致；普通桌面使用建议保留默认路径。

Claude Code 为可选 provider：将 `claude` 加入 `USAGE_PROVIDERS`，安装后运行 setup 并显式重启用量 worker。采集器读取 Claude Code 的 macOS Keychain OAuth 凭据（或 CLI 的凭据文件），展示 `5h` / `7d` 两行 session / week 已用量；登录和 token 刷新仍由 Claude Code 管理。请求头通过 stdin 传给 curl，不把 token 放入命令参数。支持主 socket 和额外实例独立写入，失败时不更新时间戳；短期缓存、429 退避沿用上游采集器。可选 `m7d` 模型周额度和 `spend` 额外消费也能展示，`spend |none|` 隐藏。

OpenCode Go 为可选 provider：将 `opencode-go` 加入 `USAGE_PROVIDERS` 后重新运行 setup，并显式重启用量 worker。
采集器默认只读取 Pi 的 `~/.pi/agent/auth.json` 中 `opencode-go.key`；可以用 `SENTINEL_OPENCODE_GO_AUTH_FILE` 指定同结构凭据文件的路径，不在 env 文件中保存 key。
JS 侧栏使用 `go5h`、`go7d`、`go1m` 三个标签显示服务端已用百分比和重置倒计时；该 provider 不提供 Swift 展示兼容。
网络错误保留上次用量并标记 stale，鉴权错误清除进度并显示提示；不会把未知用量当作 0%。数据合同见 [架构说明](architecture.md)。

Grok 登录刷新由 Grok CLI 负责；出现登录错误时运行 `grok login`。Codex 登录由 Codex CLI 管理。用量载体不要运行任务或手动改名；tmux 模块在额度载体不存在时可以使用普通 workspace 的 description。

Grok 登录切换期间若暂时读不到凭据，采集器会间隔 2 秒重试，最多额外读取 3 次；这不会重复发送用量请求。
用量行固定周期列宽度，错误显示简短状态（如 `⚠ sign in`）；悬停可查看完整原因和登录提示。

正式版与 local 版共用采集器时，在 `usage-sentinels.env` 配置 `CMUX_EXTRA_SOCKETS="/tmp/cmux-staging-macos-local.sock"`。每次查询的数据分别写入主连接和额外实例；某个实例关闭、连接失败或缺少额度 workspace，不阻止其他实例更新。重新打开后下一轮会自动重试，所有实例均失败才将该 provider 的刷新标为失败。只有写入成功的实例才更新侧栏时间戳；doctor 的 provider 时间戳表示至少一个实例成功，不能代替逐实例检查。

## 日常检查

```sh
~/bin/cmux-sentinel doctor
~/bin/cmux-sentinel usage
~/bin/cmux-sentinel refresh
tmux capture-pane -p -t cmux-sentinel-refresh -S -20
```

local doctor 不发网络请求，检查 worker、启用 provider 的成功时间和最后查询结果。上游更完整的 Codex 能力诊断可单独调用 `~/bin/cmux-sentinel-doctor.sh`，该工具可能查询账户和版本。

修复 URL 处理器：

```sh
python3 ~/.config/cmux-sentinel/local/install_tmux_actions.py
```

安装器把解析到的 `tmux`、`cmux` 绝对路径（`SENTINEL_TMUX_BIN`、`SENTINEL_CMUX_BIN`）和显式 PATH 写进 URL App：cmux 由 launchd 启动，PATH 只有 `/usr/bin:/bin:/usr/sbin:/sbin`，动作进程不能再依赖 `shutil.which`。移动 Homebrew 或 cmux 安装位置后重新运行上面的命令。动作失败原因追加到 `url-action-errors.log`；该文件不存在表示近期没有失败。

## 升级与停止

先在当前仓库合并上游，再运行 `make check` 和 `./install.sh`。已运行的 Python 进程继续使用旧代码；确认需要切换时显式停止并恢复刷新服务：

```sh
tmux kill-session -t cmux-sentinel-refresh
~/bin/cmux-sentinel start
```

停止期间用量和 tmux 元数据不再更新；已加载 JS 的本地展开折叠仍可响应。若配置了其他 session 名，替换命令中的默认值。不要停止其他项目的 session。

`bin/cmux-sentinel update` 在 local 模式拒绝远程上游覆盖。源码整理后的工作区未自动部署；仓库验证不证明本机安装副本已同步。

## 上游模式与回退

`./install.sh --profile upstream` 显式运行原 Swift/launchd 安装器；其功能、启动项和 hooks 按上游行为执行。它不会移除已安装 JS，而 cmux 同名 JS 优先于 Swift。切回 Swift 前先备份并移出已安装的 `workspaces.js`，再选择 Swift 侧栏；不能只覆盖 `.swift` 就认为切换完成。

若只想退回 cmux 原侧栏，通过 cmux 界面选择内置 workspace 列表即可。上游安装、可选 Zed 和发布步骤见 [上游兼容](upstream.md)。
