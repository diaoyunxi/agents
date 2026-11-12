# document_read — 读取多格式文档

## 作用
把文档读成文本：PDF（需 pypdf）、Word/DOCX（需 python-docx）、Markdown/代码/纯文本/JSON（内置）。按扩展名自动选择读法，可强制指定 format。

## 参数
- `filePath`（string, 必填）：相对工作区的文档路径。
- `format`（string, 可选）：强制指定 `pdf`/`docx`/`md`/`code`；省略按扩展名判断。
- `pages`（string, 可选）：PDF 页码范围，如 `1` 或 `1-5`；省略为前 20 页。
- `max_chars`（integer, 可选）：最多返回字符数，默认 20000。

## 门控
- 文本/Markdown 总是可用。
- PDF 需 `pypdf`、DOCX 需 `python-docx`：缺库时返回明确安装指引（不整体停用，便于降级读文本）。

## 配合
- 表格提取用 `document_extract_tables`；读单行号代码用 `read_file`。
