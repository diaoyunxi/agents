# git_ops — Git 仓库操作

## 作用
在工作区内执行 git 命令并返回输出。只读命令（status/log/diff/show/branch/remote/tag/blame…）直接执行；写命令（commit/push/pull/reset/checkout…）实际执行并附警示。

## 参数
- `git_args`（string, 必填）：git 子命令及参数，如 `status -s`、`log --oneline -10`、`diff --staged`。
- `cwd`（string, 可选）：仓库目录（相对工作区），默认工作区根。
- `timeout`（integer, 可选）：默认 120 秒。

## 门控
声明 `REQUIRES=["cli:git"]`：本机未装 git 时自动停用；`git` 不在 PATH 请安装。

## 注意事项
- 高风险（push/reset --hard/rebase）前先 `request_approval`。
- 远程仓库鉴权（HTTPS token / SSH key）由本机 git 配置承担。
