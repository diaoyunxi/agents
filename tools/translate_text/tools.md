# translate_text — 文本翻译

## 作用
翻译文本。默认走 MyMemory 免密钥接口（自动分片，长文也能翻）；也可在 `config.json` 的 `custom.translate` 配置自己的翻译 API（`api_url` / `api_key`），配置后优先使用。

## 参数
- `text`（string, 必填）：要翻译的文本。
- `target`（string, 必填）：目标语言 ISO 代码，如 `en`、`zh`。
- `source`（string, 可选）：源语言 ISO 代码；省略则自动检测。
- `max_chars`（integer, 可选）：最多返回字符数，默认 4000。

## 返回
`[源语言 -> 目标语言] 译文`。

## 注意事项
- 代码、专有名词、标识符原样保留，只翻译自然语言。
- 术语对照请结合 `web_search` 查官方译法。
