# python_execute — 执行 Python 代码

## 作用
执行一段 Python 源码（写入工作区临时脚本、用当前解释器运行、超时受限），回显 exit_code / stdout / stderr。适合数据清洗、统计、脚本验证与快速计算。

## 参数
- `code`（string, 必填）：要执行的 Python 源码。
- `timeout`（integer, 可选）：默认 30 秒，最大 300 秒。
- `stdin`（string, 可选）：写入标准输入的内容。

## 返回
`exit_code`、`--- stdout ---`、`--- stderr ---`（各截断）。临时脚本执行后自动清理。

## 门控与安全
- 始终可用（本运行时即 Python）；缺 `numpy`/`pandas` 等库时，涉及它们的代码会报错。
- `DANGEROUS`：可执行任意代码，写操作前请确认影响。
