# web_search — 联网搜索

## 作用

联网搜索并返回结果列表（标题 + 链接 + 摘要）。默认使用 DuckDuckGo（无需密钥）；也可在 `config.json` 的 `web_search` 一节配置 `provider` 为 `brave` 或 `tavily` 并填写 `api_key`。

## 参数

- `query`（string, 必填）：搜索关键词。
- `max_results`（integer, 可选）：最多返回条数，默认 8，最大 20。
- `timeout`（integer, 可选）：超时秒数，默认 20。

## 返回

编号结果列表：标题、URL、摘要；末尾提示可用 `web_fetch` 深入阅读。

## 注意事项

- 关键词要具体（包含版本号、报错信息、专有名词），可适当用英文搜索技术资料。
- 默认按 DuckDuckGo（html → lite）→ Bing 的顺序兜底；个别网络环境下 DuckDuckGo 不可达时会自动改用 Bing。
- 搜索结果只是线索，引用前用 `web_fetch` 打开原文核对。
