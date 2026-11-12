# wikipedia_lookup — 百科查询

## 作用
查询维基百科条目（REST API，免密钥）：返回条目标题、简介、正文若干段落。默认中文，可指定语言版本。

## 参数
- `title`（string, 必填）：条目标题，如 `变压器`、`Transformer (electronics)`。
- `lang`（string, 可选）：语言版本，默认 `zh`，可用 `en`/`ja`/`de` 等。
- `paragraphs`（integer, 可选）：正文最多取段落数，默认 5。
- `timeout`（integer, 可选）：默认 20 秒。

## 返回
条目名、简介、页面链接与正文节选。

## 注意事项
- 找不到条目会提示换语言或改名；歧义条目用「标题 (消歧义)」形式。
- 深度事实仍建议结合 `web_search` 交叉核对。
