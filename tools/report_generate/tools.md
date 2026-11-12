# report_generate — 生成结构化报告（产出）

## 作用
把已收集到的信息组织成结构化 Markdown 报告，并保存到工作区文件（含标题、时间戳、章节、结论）。无额外依赖。

## 参数
- `title`（string, 必填）：报告标题。
- `sections`（array, 必填）：章节数组，每项 `{"heading": "章节名", "content": "Markdown 正文"}`。
- `conclusion`（string, 可选）：结论/建议。
- `outputPath`（string, 可选）：输出路径，默认 `report_YYYYMMDD-HHMMSS.md`。

## 返回
`已生成报告 <路径>（N 章节，M 字符）`。

## 配合
- 内容来源：先用 `web_search` / `read_webpage` / `document_read` / `data_analyze` 收集，再汇总成报告。
