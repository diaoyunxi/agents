# search_files — 搜索文件

## 作用

在工作区内按文件名或文件内容进行搜索，用来定位某个函数、配置项、错误信息出现在哪个文件哪一行。

## 参数

- `pattern`（string, 必填）：要搜索的关键词；当 `regex` 为 `true` 时按正则表达式解析，否则为普通子串匹配。
- `path`（string, 可选）：限定搜索的子目录，默认整个工作区。
- `glob`（string, 可选）：文件名过滤，例如 `*.py`；省略时搜索常见代码与文本文件（py/md/txt/json/js/ts/html/css/yaml/toml）。
- `regex`（boolean, 可选）：是否启用正则，默认 `false`。
- `ignore_case`（boolean, 可选）：是否忽略大小写，默认 `true`。
- `max_results`（integer, 可选）：最多返回条数，默认 100。

## 返回

分「文件名匹配」与「内容匹配」两段，内容匹配每行为 `相对路径:行号: 该行内容`。

## 注意事项

- 先用普通关键词粗定位，再切换 `regex=true` 精确定义式效果更好。
- 命中过多时请补充 `path` 或 `glob` 缩小范围。
- `.git`、`node_modules`、`__pycache__` 等目录会被跳过。
