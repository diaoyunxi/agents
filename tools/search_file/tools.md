# search_file — 按模式搜索文件

## 作用

按通配符模式递归搜索文件或目录名，用来批量定位同类文件（例如所有 Python 文件、所有测试文件、所有名为 config 的文件）。

## 参数

- `pattern`（string, 必填）：通配符模式，例如 `*.py`、`test_*.js`、`*config*`。匹配的是文件名/目录名本身。
- `path`（string, 可选）：限定搜索的目录，默认整个工作区。
- `recursive`（boolean, 可选）：是否递归子目录，默认 `true`。
- `ignore_globs`（array<string>, 可选）：额外忽略的通配符模式，匹配路径任意一级，例如 `["node_modules", "*.min.js"]`。
- `max_results`（integer, 可选）：最多返回条数，默认 200。

## 返回

匹配路径清单（相对工作区），目录带 `/` 后缀；无匹配时明确提示。

## 注意事项

- 本工具只匹配**文件名**；要按文件内容搜索请使用 `search_content`。
- `.git`、`node_modules`、`__pycache__` 等目录会自动跳过，也可用 `ignore_globs` 补充排除。
- 命中过多时缩小 `path` 或细化 `pattern`。
