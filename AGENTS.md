# cmux-sentinel

本项目是 macOS cmux 自定义侧栏：JS 展示 workspace、GPT/Codex 与 Grok 用量和 tmux 会话，Python worker 负责采集、元数据同步和本机 URL 动作。保留上游 shell 工具与 Swift 兼容模式。

## 重要约束

- 当前目录是唯一 Git 根目录；Python 正式代码在 `src/`，沿用上游 `bin/`、`hooks/`、`sidebars/` 的路径惯例。
- `CLAUDE.md` 只路由到本文件。知识放 `docs/`，验证放 `tests/`，维护自动化放 `scripts/`；临时文件统一放忽略的 `scratch/`。
- 默认使用 local JS/tmux 安装模式；upstream Swift/launchd 必须显式选择。修改源码不等于部署，不自动重启服务或安装登录启动项。
- 用量凭据留在提供方的凭据存储中；不复制到源码、日志、侧栏或命令参数。Grok 协议改编须保留 `LICENSE-CC-Switch`。
- workspace 额度以 title 标签识别；不要保存位置型 ref。description 写入统一经 `sidebar_metadata.py`，不可绕过共享锁。
- tmux 关闭动作必须校验签名、socket/server/session 身份以及最新常驻标注；不要将名称、备注当作命令执行。
- 长驻任务使用 tmux，并填写 `@project`、`@lifecycle`、`@note`、`@port`；不结束其他任务的会话。

## 验证改动

- `make ci`：shellcheck、秘密检查、Markdown、打包检查、Python/JS 便携测试及上游离线测试。
- `make check`：在以上检查外，使用已安装 cmux JS 运行时验证交互，并验证仓库 JS 侧栏；需要 macOS/cmux。
- `make test-local`：本地扩展的隔离测试；`make test-upstream`：保留的 shell 测试。
- UI 变更还应目视检查；解释器通过不等于像素验证。`make sidebar-live` 会临时打开面板，需要部署范围授权。
- 不为小型文案改动编写测试；改动通过对应检查后不要无故重复全套测试。清理本次无用临时文件。

## 任务阅读路由

- 项目入门和安装：`README.md`、`docs/operations.md`。
- 模块、数据流、兼容边界：`docs/architecture.md`。
- 开发、测试和源码路径调整：`CONTRIBUTING.md`。
- 额度协议与 Swift 兼容：`docs/architecture.md` 和对应采集器、测试。
- 上游安装、Zed 和发布：`docs/upstream.md`；不将其安装命令用于默认 local 模式。
- 项目知识收尾使用可用的 neat-freak skill；真实 cmux 操作使用 cmux skill。
