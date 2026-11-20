# sandbox_execute — 隔离沙箱执行（治理/安全）

## 作用
在隔离环境中执行命令：默认**断网**（代理指向不可达地址）、在**全新临时目录**运行、限定超时，结束后自动清理。比 `execute_command` 更保守，适合跑不受信的脚本。

## 参数
- `command`（string, 必填）：要执行的命令行（在沙箱内运行）。
- `allow_network`（boolean, 可选）：是否允许网络，默认 false（断网）。
- `timeout`（integer, 可选）：超时秒数，默认 30，最大 300。

## 返回
网络状态、`$ 命令`、exit_code、stdout/stderr（截断）；默认断网时会提示。

## 注意事项
- `DANGEROUS`：可执行任意命令，隔离不等于完全安全；破坏性命令仍需谨慎。
- 需要正常网络/工作区依赖时用 `execute_command`；需要 Python/JS 时用 `python_execute`/`javascript_execute`。
