# 上游兼容与发布

本项目保留上游 shell、hooks、Swift 和发布设施；默认 JS/tmux 模式见 [运维说明](operations.md)。本页只用于显式 upstream 模式，不能用远程上游安装器覆盖本地扩展。

## 安装与维护

依赖 macOS、cmux、jq、curl、git，以及所选 provider 的 CLI / 登录凭据。

```sh
./install.sh --profile upstream
CMUX_SENTINEL_PROFILE=upstream ~/bin/cmux-sentinel setup
CMUX_SENTINEL_PROFILE=upstream ~/bin/cmux-sentinel usage
CMUX_SENTINEL_PROFILE=upstream ~/bin/cmux-sentinel paint
~/bin/cmux-sentinel-doctor.sh
```

安装器复制 Swift、shell 工具和 `docs/examples/` 模板，备份被替换文件，默认执行 setup、刷新用量并重载侧栏；`--no-setup` 只准备文件。已有配置保留；新配置默认 `USAGE_PROVIDERS="claude"`，支持 `claude codex amp`。从 local 切换时需自行调整 provider，并按运维说明移出同名 JS。

| 可选项 | 用途 |
| --- | --- |
| `--with-bridge` / `WITH_BRIDGE=1` | 注册 Claude 状态 hooks；之后重启 Claude Code |
| `--with-amp` / `WITH_AMP=1` | 安装 Amp 插件和共享 bridge，不注册 Claude hooks |
| `--with-zed` / `WITH_ZED=1` | 安装 Zed 工具和 hooks，见下节 |
| `--reload-agents` / `RELOAD_AGENTS=1` | 只重新加载内容已变且正在加载的 LaunchAgent |
| `CLAUDE_MODEL_METER=1` | 启用可选模型周额度，再运行 setup |
| `AMP_ORB_METER=1` | 启用可选 orb 额度，再运行 setup |

自动刷新需在 `~/.config/cmux/cmux.json` 合并 `"automation": { "socketControlMode": "automation" }`，保留原有配置，再执行 `cmux reload-config`。仅为已启用且尚未加载的 provider 启动对应任务，例如 Codex：

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cmux-codex-usage.plist
```

Claude / Amp 分别使用 `com.cmux-claude-usage.plist` / `com.cmux-amp-usage.plist`。已加载 plist 不会随文件修改自动更新，按安装器打印的命令重新加载，或使用 `--reload-agents`。组名同步仅供旧版 cmux：设置 `GROUP_NAME_SYNC=1`，先运行 `~/bin/cmux-group-sync.sh --list` 查看，再按需启用对应任务。

各采集器支持 `--print`（查询）、`--update`（写入侧栏）；更多参数见脚本入口。禁用 provider 后采集器停止更新，已有额度 workspace 需自行关闭。缺失数据不当作 0%。Codex 数据合同见 [架构说明](architecture.md)。

- Claude：`bin/cmux-claude-usage.sh` 从提供方凭据存储读取令牌，查询 OAuth usage 接口；登录刷新由 Claude Code 管理，重置时间采用服务端值。
- Amp：`bin/cmux-amp-usage.sh` 解析 `amp usage` 中 `other usage` / `orb usage` 前的剩余百分比，换算为已用；解析失败显示未知。`--raw` 可能含邮箱，仅用于本机调试。
- hooks：静态 title 标记表示 working / compacting / waiting；共享 bridge 按会话计数。`CMUX_SENTINEL_WORK_TTL` 默认 3600 秒，等待用户状态不按该计时过期。`CMUX_SENTINEL_NOTIFY_CMD` 可配置进入等待状态时的通知命令。
- Amp 原生侧栏插件另用 `cmux hooks amp install` 安装；不要修改 cmux 管理的 `cmux-session.ts`。可选 `CMUX_SENTINEL_AMP_ASK=1` 会改变工具确认行为。

## Zed

Zed 集成默认关闭，保留当前 worktree 跳转、终端状态元数据和用量 TUI；没有实现 Zed fork 面板。

```sh
./install.sh --profile upstream --with-zed
```

需要状态 hooks 时，在个人 shell 配置添加 `export ZED_SENTINEL=1`，重启 Claude Code。需要 `ze` / `Ctrl-O` 跳转时添加：

```sh
eval "$(~/bin/cmux-open-in-zed.sh --shell-init)"
```

`~/bin/zed-usage-tui.sh` 需自行在终端运行，支持 `--once`；`ZED_USAGE_INTERVAL` 默认 30 秒。跳转和 TUI 均只在调用时运行。

`hooks/zed-bridge.sh` 受 `ZED_SENTINEL=1` 控制，输出 OSC-2 元数据和 `ZED_SENTINEL_STATE_DIR` 下的 JSON；分别可用 `ZED_SENTINEL_OSC=0` / `ZED_SENTINEL_FILE=0` 关闭。不要假设 OSC-2 会改变 Zed 原生标签标题。停用时取消 `ZED_SENTINEL`，移除个人 shell 初始化行和对应 Claude hooks。

## 发布

当前 Homebrew 配方对应上游 v0.2.3，本地扩展未另行发布。发布自动化仍指向上游仓库；若将来发布 fork，先调整仓库和 tap 目标。

1. 修改 `VERSION`，在 `CHANGELOG.md` 写同版本标题，运行 `make check` 后提交。
2. 创建并推送匹配的 `vX.Y.Z` 标签；`.github/workflows/release.yml` 自动生成 GitHub Release，正文来自对应 changelog。只有最高版本标记 Latest，补发旧版可用该 workflow 的 `workflow_dispatch`。
3. 标签可下载后运行 `scripts/make-formula.sh`、`make formula`，提交生成的配方；不要手改 version、URL 或 SHA256。
4. 将配方同步到上游独立仓库 `oliver-kriska/homebrew-tap` 的 `Formula/cmux-sentinel.rb`，验证 `brew test cmux-sentinel` 和 `brew audit --strict --online oliver-kriska/tap/cmux-sentinel`。

Homebrew 只更新其安装目录；升级后还需部署到用户目录，才能更新实际使用的脚本：

```sh
brew upgrade cmux-sentinel
CMUX_SENTINEL_PROFILE=upstream cmux-sentinel deploy
```

`deploy` 拒绝降级或同版本不同指纹覆盖，`--force` 才覆盖；不要用它意外回退本地扩展。`brew services` 不管理这组独立 LaunchAgent。安装指纹记录在 `~/.config/cmux-sentinel/VERSION`，可通过 `cmux-sentinel version` 查看。
