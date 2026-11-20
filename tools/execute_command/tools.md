# execute_command — 执行命令行

## 作用

在工作区目录下执行一条 Shell / PowerShell 命令并返回标准输出、错误输出与退出码。适用于执行 git、pip、pytest、构建等本机操作。

## 参数

- `command`（string, 必填）：要执行的完整命令行字符串，会通过系统 shell 执行。Windows 上默认经 `cmd.exe`；需要 PowerShell 语法时可写 `powershell -NoProfile -Command "..."`。
- `timeout`（integer, 可选）：超时秒数，默认 120，最大 600。
- `cwd`（string, 可选）：执行目录（相对工作区），默认为工作区根目录。

## 返回

依次为：命令行回显、`cwd` 路径、`exit_code`、`--- stdout ---` 输出、`--- stderr ---` 错误输出。

## 注意事项

- 命令输出较长时会截断（stdout 最多 20000 字符），必要时重定向到文件再 `read_file`。
- 危险命令（如格式化磁盘、删除根目录等）会被安全策略直接拒绝，请改用更安全的方式。
- 这是一个高风险工具：仅在确有需要时使用，纯文件操作请优先使用 `read_file` / `write_to_file` / `replace_in_file` / `delete_file`。
- 可在设置页的「禁用列表」中关闭本工具。
