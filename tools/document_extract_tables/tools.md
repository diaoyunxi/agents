# document_extract_tables — 表格提取

## 作用
从表格文件中提取数据：CSV/TSV 用内置解析（总可用）；XLSX/XLSM 用 openpyxl（缺库时该项降级并给出安装指引）。可按索引取工作表。

## 参数
- `filePath`（string, 必填）：表格文件路径（csv/tsv/xlsx）。
- `table_index`（integer, 可选）：XLSX 取第 N 个工作表（0 起），默认 0。
- `limit`（integer, 可选）：最多返回行数，默认 50。

## 返回
工作表/列名 + 制表符分隔的数据行。

## 门控
工具整体保持可用（CSV 走内置）；XLSX 需 `openpyxl`，缺失时仅 xlsx 分支返回安装指引。
