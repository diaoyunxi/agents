# search_content — 文件内容搜索

## 作用

基于 ripgrep 的文件内容搜索：用正则表达式在工作区内查找匹配的行，返回 `路径:行号: 内容`，可带上下文行。用于定位函数定义、配置项、错误信息、某个符号的所有引用。

## 参数

- `pattern`（string, 必填）：正则表达式（ripgrep 语法），例如 `def run_chat`、`TODO|FIXME`、`api\.(get|post)\(`。
- `path`（string, 可选）：限定搜索的目录，默认整个工作区。
- `glob`（string, 可选）：文件名过滤，例如 `*.py`、`**/*.ts`；省略时只搜索常见文本文件。
- `caseSensitive`（boolean, 可选）：是否区分大小写，默认 `false`。
- `contextBefore` / `contextAfter`（integer, 可选）：每个匹配前/后显示的行数，默认 0，最大 20。
- `contextAround`（integer, 可选）：匹配前后各显示的行数，设置后覆盖上面两项。
- `outputMode`（string, 可选）：`content`=匹配行（默认）；`count`=每个文件的命中数；`files_with_matches`=仅返回文件路径。
- `ignore_globs`（array<string>, 可选）：额外忽略的通配符模式，例如 `["*.log", "dist"]`。
- `maxResults`（integer, 可选）：最多返回条数，默认 100，最大 500。

## 返回

匹配行清单，格式为 `相对路径:行号: 该行内容`；上下文行以 `路径-行号- 内容` 区分。优先调用系统里的 `rg`，未安装时自动使用内置搜索引擎（同样尊重 `.gitignore`）。

## 注意事项

- 按**文件名**查找请用 `search_file`，按内容查找用本工具。
- 正则尽量具体；命中过多时补充 `path`、`glob` 或 `ignore_globs` 缩小范围。
- `.git`、`node_modules`、`__pycache__`、`.gitignore` 命中项与大文件（>2MB）会被跳过。
- 安装 ripgrep 可获得最佳性能：Windows 可用 `winget install BurntSushi.ripgrep.MSVC` 或 `scoop install ripgrep`。
