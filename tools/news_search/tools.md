# news_search — 新闻搜索

## 作用
按关键词搜索新闻，返回标题、来源、链接与摘要。默认走 DuckDuckGo News（免密钥）；`config.json` 的 `web_search.provider` 设为 `brave` 并填 `api_key` 时走 Brave News API。

## 参数
- `query`（string, 必填）：新闻关键词。
- `max_results`（integer, 可选）：最多返回条数，默认 8，最大 20。
- `timeout`（integer, 可选）：超时秒数，默认 20。

## 返回
编号新闻列表（标题 / 链接 / 摘要）。

## 注意事项
- 时效性强的事件优先用它，而非通用 `web_search`；历史/事实类用 `web_search` 或 `wikipedia_lookup`。
- 结果只是线索，引用前用 `web_fetch` 打开原文核对日期与出处。
