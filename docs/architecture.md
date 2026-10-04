# 架构与模块边界

## 当前 local 模式

```text
Claude Code OAuth → bin/cmux-claude-usage.sh ┐
Codex CLI → bin/cmux-codex-usage.sh ─┤
Grok 凭据 → src/grok_usage.py ──────┼→ 额度 workspace title / progress
Pi Go 凭据 → src/opencode_go_usage.py ┤
                  src/refresh.py ─┴→ 时间戳

tmux → src/tmux_sidebar.py → src/sidebar_metadata.py → workspace description
                                                    ↓
                                      sidebars/workspaces.js
                                                    ↓ cmux-sentinel://
注册的 macOS URL App → src/action_handler.py → src/tmux_actions.py
```

- `sentinel_config.py` 集中管理路径、命令发现、provider 和 session 配置；源码和安装副本使用同一模块。
- `refresh.py` 按启用的 provider 每 300 秒查询额度；不调用模型。主 socket 与 `CMUX_EXTRA_SOCKETS` 中的实例独立写入，同一份查询结果复用；一个实例失败不会中断其余实例。Claude / Codex poller 通过 `sentinel-socket-updated:` 输出逐实例成功结果，worker 只为这些实例写入新鲜度时间戳。
- `opencode_go_usage.py` 使用 Pi 保存的 Go key 读取官方用量接口，发布 session、week、month 三个窗口；凭据不复制到本项目。
- `tmux_sidebar.py` 每 5 秒采集会话元数据和签名动作链接；不生成或重写 JS 文件。
- `sidebar_metadata.py` 是 description 的唯一读改写入口，进程间文件锁覆盖读取和写入，保留用户说明和其他受管字段。锁只协调本项目进程，无法阻止用户或其他程序同时修改同一字段。
- 每个有 workspace 的窗口选择一个数据载体，优先 `cx7d`、`cx5h`、`grokcredits`，否则复用普通 workspace；不新增专用 workspace。没有 workspace 的窗口不能接收数据。更换载体时移除其他 workspace 上的旧元数据。
- `workspaces.js` 从任一 workspace 读取 `sentinel-tmux:` JSON。本地 signal 保存展开、确认和折叠状态；短暂缺失数据时保留快照。展开行里的端口标签是唯一对外链接：只有纯数字 `@port` 会拼成 `http://127.0.0.1:<port>` 交给宿主 `openURL`，其余标注照原样展示；不探测端口，也不经过签名动作。
- `tmux_actions.py` 负责身份、签名、关闭策略和布局存储；`action_handler.py` 组合执行动作与刷新，不让动作模块反向依赖采集器。
- URL App 由 `scripts/install_tmux_actions.py` 注册，并把 `tmux`、`cmux` 绝对路径和显式 PATH 固化进 applet：cmux 由 launchd 启动，环境里没有 Homebrew 路径，动作进程解析不了命令。动作异常追加到 `~/.local/state/cmux-sentinel/url-action-errors.log`，超 64 KiB 时重写。

## 状态与数据合同

- 用量 title 是持久识别锚点；`progress` 和 description 时间戳用于展示。百分比表示已用量。
- `sentinel-updated:<epoch>` 表示最近成功的用量更新时间；UI 超过 900 秒显示 stale。
- `sentinel-tmux:` 后是完整 JSON 快照：`sessions`、`pending`、`layout`。不在其中放凭据。
- 用量快照、布局、签名密钥和读改写锁默认在 `~/.local/state/cmux-sentinel/`；密钥和状态文件使用 0600。
- URL 动作绑定 socket、server PID、session ID、创建时间和动作类型；确认关闭还绑定备注与生命周期。关闭前重新读取身份及标注。
- 原命令控制台和笔记路由保持退役；收到旧链接不会执行命令或改写笔记。

## 兼容边界

Swift 不是根据安装目录的文件残留自动选择的运行模式。默认 worker 只发布 JS 元数据；需要旧的动态 Swift 面板时，明确运行 `python3 src/tmux_sidebar.py --renderer swift --once`。Swift 生成逻辑隔离在 `src/tmux_swift.py`，两种 UI 不承诺功能完全一致。

原有 shell 路径保留，以免破坏上游测试、hooks 和显式 upstream 安装。`install.sh` 是统一安装入口，默认转交 `scripts/install_local.py`，只有 `--profile upstream` 才进入原版 Swift/launchd 安装流程。

安装的 Python 路径保留 `~/.config/cmux-sentinel/local/`，服务路径不依赖源码仓库所在位置。旧安装的 `tmux_actions.py` 曾兼任 URL 入口；重新注册后改为 `action_handler.py`。

## 用量数据合同

- Claude：`bin/cmux-claude-usage.sh` 读取 CLI 的 OAuth 凭据并查询用量接口；保留上游缓存、429 退避、过期数据标记与可选模型/额外消费行。一次查询复用到每个 cmux socket，仅完全写入成功的实例输出新鲜度标记，由 worker 通过共享锁更新时间戳。
- Codex：`bin/cmux-codex-usage.sh` 每轮启动短命 stdio app server，调用 `account/rateLimits/read`，由 Codex 管理鉴权和刷新。只用 `rateLimits` 驱动侧栏；按 `windowDurationMins` 分桶，小于一天为 `cx5h`，否则为 `cx7d`，不依赖 primary / secondary 顺序。未知时长不猜测，不退回读取 OAuth 或本地 rollout。
- Codex 的额外 named limits 和 reset credits 仅用于诊断，不创建 workspace、不兑换额度。正常 `--raw` 移除账户相关 credit ID；`--raw-full` 仅限本机私密调试。
- Grok：`src/grok_usage.py` 读取 Grok CLI 凭据，查询 `GetGrokCreditsConfig`，协议改编自 CC Switch v3.20.1 的 `subscription_grok.rs`，保留根目录 `LICENSE-CC-Switch`。UI 使用 week 标签，重置时间取实际响应。
- OpenCode Go：`src/opencode_go_usage.py` 使用 Pi 保存的 key，以 Bearer 鉴权请求 `GET https://opencode.ai/zen/go/v1/usage`。`usage.rolling / weekly / monthly` 对应 `go5h / go7d / go1m`，读取 `percent`、`resetsAt` 和 `status`（`ok` / `rate-limited`）；不反推美元或自行计算重置周期。
- Go 请求设置明确 User-Agent，拒绝重定向，区分鉴权、订阅、Cloudflare、限流和网络错误；暂时性错误保留旧值并标 stale，其他错误清除进度。不会静默切换凭据来源或将未知用量当作 0%。配置见 [运维说明](operations.md)。

Go 接口原始依据固定在 [usage 路由](https://github.com/anomalyco/opencode/blob/0f549842ee746e400b1f72516b0b2e292e267e2c/packages/console/app/src/routes/zen/go/v1/usage.ts) 与同提交的 `packages/console/core/src/subscription.ts`；本项目实际支持范围以采集器和隔离测试为准。

## Swift 维护注意事项

以下来自 cmux 0.64.20–0.64.24 的历史验证，仅用于保留的 Swift 兼容实现；升级后以 `tests/check_sidebar_runtime.py` 和实际界面重新核验。

- 同名 JS 优先于 Swift；检查前先确认加载的文件。`progress`、`description`、`color` 可绑定，但未设置时为空；`set-status` 不进入自定义侧栏。数据 snapshot 可能遗漏字段，不能用它代替已知赋值的渲染探针。
- `workspaces` / `clock` 绑定放在 view builder 内；可空值使用 `if let`，数组用 `.count > 0`。不要依赖 `!= nil`、循环内赋值或循环内 `return`；计数用 `.filter { … }.count`。
- 避免彩色 `Divider().background(...)`、无限高度 frame 和分隔线 overlay；它们曾导致布局膨胀。整行点击用非零背景填充，字体用 system / monospaced。
- title 状态标记保持静态，动画标题会产生频繁更新。分组和快捷键使用 group / anchor 数据，不从 `w.index` 推算。
- 空白面板先缩到 `Text("HELLO")`，再逐项恢复。旧成功画面可能掩盖新解释失败；validate 成功也不代表真实数据分支或像素正常。

## 验证层次

- `make test-local`：无账号、无真实 tmux/cmux 操作的 Python 行为测试和 JS 逻辑测试。
- `make test-upstream`：保留的 shell 协议、安装与入口离线回归；真实 Amp 插件验证单列 `make amp-live`。
- `make runtime-js`：加载安装版 cmux 原始 JS 运行时，拦截外部动作，验证响应式交互。
- `make sidebar`：暂存仓库 JS 并进行 cmux 解释验证，结束后删除暂存文件。
- `make sidebar-live`：临时挂载 JS 面板，需人工观察，不能将命令成功当作渲染成功。
