# rss_read — 读取 RSS/Atom 订阅

## 作用
读取一个 RSS/Atom 订阅源的最新条目：标题、链接、时间、摘要。内置 XML 解析（无额外依赖）。

## 参数
- `url`（string, 必填）：订阅源 URL（http/https）。
- `max_items`（integer, 可选）：最多返回条目数，默认 15。
- `timeout`（integer, 可选）：默认 30 秒。

## 返回
订阅源名 + 编号条目列表。

## 注意事项
- 非常规格式可能解析不到条目；正文深入用 `web_fetch` 打开条目链接。
- 需要更多新闻源时配合 `news_search`。
