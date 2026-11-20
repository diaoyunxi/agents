# fix_capabilities — 批量补齐缺失依赖（自动启用恢复）

## 作用
扫描当前被「按硬件自动启用」门控停用的工具，自动收集它们缺失的 Python 包（`pkg:` 能力项），一次性 `pip install`，装完刷新能力缓存使这些工具恢复启用。

## 参数
- `only`（array, 可选）：只修指定工具缺失的包（工具名列表）；省略则修全部被停用工具。
- `dry_run`（boolean, 可选）：true 时只列出要装的包、不实际安装，默认 false。
- `timeout`（integer, 可选）：默认 600 秒，最大 1800 秒。

## 返回
被停用工具及各自缺失包清单；实际执行的 pip 命令与结果；成功时列出已恢复启用的工具。

## 边界
- 只处理 Python 包（`pkg:`）。CLI（`cli:git`/`cli:node`/`cli:docker`）、GPU（`gpu:nvidia`）不是 pip 包，需要单独安装对应程序，本工具不会处理。
- 本质是调用 `pip_install` 工具，`DANGEROUS`。

## 示例
本机缺 `sympy`/`matplotlib` 时，调用 `fix_capabilities` 会安装这两个包并恢复 `symbolic_math`、`chart_generate`。
