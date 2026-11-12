# pip_install — 安装 Python 包

## 作用
用当前解释器的 pip 安装一个或多个 Python 包（支持指定版本 `pkg==x.y`、约束文件、升级）。安装成功后自动刷新 `capabilities` 缓存，被门控停用的工具随之恢复。

## 参数
- `packages`（array, 必填）：包名列表，如 `["sympy", "matplotlib>=3.5"]`。
- `constraints_file`（string, 可选）：`-c` 约束文件路径。
- `upgrade`（boolean, 可选）：是否升级已存在包，默认 false。
- `timeout`（integer, 可选）：默认 300 秒，最大 1800 秒。

## 返回
执行的 pip 命令、exit_code、stdout/stderr；成功时附「已刷新能力缓存」提示。

## 安全
- `DANGEROUS`：可改变运行环境。禁止 `--system` / 系统前缀等包级标志（会被拒绝）。
- 装到当前解释器环境（`sys.executable -m pip`）。

## 配合
- 只想「让被停用的工具恢复」用 `fix_capabilities`（自动收集缺失包批量装）。
- 装完 `git_ops`/`javascript_execute` 等 CLI 门控工具仍需装对应可执行程序（pip 装不了 CLI）。
