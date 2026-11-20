# data_analyze — 数据分析

## 作用
对表格数据做描述统计、分组聚合、透视、去重清洗（pandas）。支持 CSV/JSON 文件或内联 JSON 行数组。

## 参数
- `source`（string, 必填）：文件路径（csv/json）或内联 JSON 行数组字符串。
- `operation`（string, 必填）：`describe`/`group`/`pivot`/`head`/`unique`/`clean`。
- `group_by`（string, 可选）：group/pivot 的分组列。
- `value_col`（string, 可选）：数值列；省略取首个数值列。
- `agg`（string, 可选）：sum/count/min/max/mean/std，默认 mean。
- `rows`（integer, 可选）：head 行数，默认 10。

## 门控
声明 `REQUIRES=["pkg:pandas"]`：未安装 pandas 时自动停用；`pip install pandas` 后恢复。

## 配合
- 生成图表用 `chart_generate`；导出表格用 `execute_command` 调 pandas 脚本。
