# web_fetch — 抓取网页内容

## 作用

抓取指定 URL 的内容并转换为 Markdown 文本：自动提取 `<title>`、meta description 与正文（标题、段落、链接、列表、代码块、表格），用于阅读文档、博客、API 说明等页面。

## 参数

- `url`（string, 必填）：完整 http(s) URL。
- `max_chars`（integer, 可选）：最多返回字符数，默认 50000。
- `timeout`（integer, 可选）：超时秒数，默认 30。

## 返回

`URL / Content-Type / 字节数` 头部 + `Title` / `Description` + Markdown 正文；JSON 与纯文本按原格式返回（JSON 会美化）。

## 注意事项

- 自动跟随重定向；头部里的 URL 是最终地址。
- 依赖 JS 渲染的页面可能提取不到文本（返回明确提示），此时可换数据源 URL。
- 单次下载上限 6MB，超出会截断。
- 找不到资料 URL 时，先用 `web_search` 搜索。
