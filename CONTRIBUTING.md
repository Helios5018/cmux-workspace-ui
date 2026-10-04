# 开发说明

先阅读 [AGENTS.md](AGENTS.md) 和 [架构说明](docs/architecture.md)。本仓库默认维护 JS/tmux local 模式，同时保留上游 shell/Swift 兼容实现。

## 修改位置

- 后端与配置：`src/`。小型无第三方依赖的 Python 模块，使用共享配置和 description 写入口。
- UI：`sidebars/workspaces.js`。Swift 回退在同目录，动态生成代码在 `src/tmux_swift.py`。
- 安装：入口 `install.sh`，local 实现在 `scripts/install_local.py`，URL App 注册在 `scripts/install_tmux_actions.py`。
- 测试：`tests/`。隔离 HOME、外部命令和状态目录，不创建真实 workspace 或关闭真实 tmux session。
- 规则只维护 `AGENTS.md`；`CLAUDE.md` 导入它。项目知识进 `docs/`，临时文件进忽略的 `scratch/`。

## 检查命令

```sh
make test-local
make test-upstream
make ci
make check
```

`make ci` 可在 Linux 运行，包含 Python 测试、JS 逻辑测试、上游 shell 回归和现有 lint。`make check` 还需要本机 cmux：运行原始 JS 响应式运行时测试，并暂存仓库 JS 进行解释验证。运行时不在标准 app 位置时设置 `CMUX_SIDEBAR_RUNTIME`。

真实 Amp 插件验证单列为 `make amp-live`，显式调用本机 Amp CLI；便携测试不根据本机是否安装 Amp 自动执行它。

UI 目视验证使用 `make sidebar-live`，它会临时打开面板并清理。不要把便携逻辑测试、运行时节点测试或解释成功说成像素检查通过。Swift 兼容可单独执行 `python3 tests/check_sidebar_runtime.py`。

Python 测试不依赖包安装：Makefile 设置 `PYTHONPATH=src:scripts`，用 `python3 -B` 避免缓存残留。安装回归使用临时 HOME 和 `--no-setup --no-actions`，并通过命令替身验证完整安装流程。

秘密检查覆盖 Git 已跟踪及未忽略的新文件。新增源码不需要先暂存才能进入检查；但最终仍须显式提交才能进入 Git 历史。不要把 credentials、真实 workspace UUID、用户绝对主目录写进可提交文件。

## 上游与发布

`bin/`、`hooks/`、上游 shell 测试和打包路径继续沿用。修改安装载荷时，保持 `install.sh`、`bin/cmux-sentinel` 与 `scripts/install_local.py` 的指纹清单一致；安装测试会交叉核对。

上游安装测试显式设置 `CMUX_SENTINEL_PROFILE=upstream`，避免当前 local 默认值改变其含义。合并上游后先通过两个测试集合，再验证本机 JS 运行时。

保留的 [发布流程](docs/upstream.md#发布) 和 Homebrew 配方描述上游版本；当前本地扩展没有另行发布。不要将源码整理、提交、部署和运行态验证混作同一个状态。
