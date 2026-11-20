# code_search — 代码搜索

## 作用
按关键词搜代码：
- `scope=local`（默认）：在工作区内搜代码/函数/模式，复用 `search_content`（按语言映射为 glob）。
- `scope=github`：给出 GitHub 公开代码检索链接（免密钥）；自动化需带 token 走 `http_request`。

## 参数
- `query`（string, 必填）：要搜的代码/模式，如 `def __init__`、`async with httpx`。
- `scope`（string, 可选）：`local` 或 `github`。
- `language`（string, 可选）：限定语言，如 `python` / `rust`。
- `glob`（string, 可选）：local 用的文件名通配，如 `*.ts`；与 language 二选一。
- `max_results`（integer, 可选）：默认 10。

## 返回
local：工作区内匹配行（路径:行号 + 内容）；github：可点开的检索链接与说明。
