# Agents · 本地智能体工作台

一个用 Python 后端驱动的本地 AI Agent。Web 端只负责展示，所有真实能力（AI 调用、工具执行、MCP、配置、文件读写）都实现在后端。

> 本文件为文档目录；全部说明文档统一存放于 `doc/`。

## 文档目录

- [00 · 概览](doc/00-overview.md)　`本文档总述`
- [01 · 快速开始](doc/01-快速开始.md)
- [02 · 目录结构](doc/02-目录结构.md)
- [03 · 界面](doc/03-界面.md)
- [04 · 自动更新](doc/04-自动更新.md)
- [05 · 配置说明（config.json）](doc/05-配置说明-config-json.md)
- [06 · 内置工具](doc/06-内置工具.md)
- [07 · 添加一个工具](doc/07-添加一个工具.md)
- [08 · 添加一个技能](doc/08-添加一个技能.md)
- [09 · 工具调用协议](doc/09-工具调用协议.md)
- [10 · 结束协议](doc/10-结束协议.md)
- [11 · MCP](doc/11-MCP.md)
- [12 · 安全说明](doc/12-安全说明.md)
- [api](doc/api.md)　`新增·代码可感知点`

> `tools/*/tools.md` 与 `skills/*.md` 是运行时由加载器读取的资源文件，保留原位，不属于文档分册。

## 保留原位的文档与资源

- [skills/code-review.md](skills/code-review.md)
- [skills/new-feature.md](skills/new-feature.md)
- [tools/ask_followup_question/tools.md](tools/ask_followup_question/tools.md)
- [tools/computer_use/tools.md](tools/computer_use/tools.md)
- [tools/delete_file/tools.md](tools/delete_file/tools.md)
- [tools/execute_command/tools.md](tools/execute_command/tools.md)
- [tools/list_dir/tools.md](tools/list_dir/tools.md)
- [tools/preview_url/tools.md](tools/preview_url/tools.md)
- [tools/read_file/tools.md](tools/read_file/tools.md)
- [tools/read_rules/tools.md](tools/read_rules/tools.md)
- [tools/replace_in_file/tools.md](tools/replace_in_file/tools.md)
- [tools/search_content/tools.md](tools/search_content/tools.md)
- [tools/search_file/tools.md](tools/search_file/tools.md)
- [tools/send_message/tools.md](tools/send_message/tools.md)
- [tools/stop/tools.md](tools/stop/tools.md)
- [tools/task/tools.md](tools/task/tools.md)
- [tools/todo_write/tools.md](tools/todo_write/tools.md)
- [tools/update_memory/tools.md](tools/update_memory/tools.md)
- [tools/web_fetch/tools.md](tools/web_fetch/tools.md)
- [tools/web_search/tools.md](tools/web_search/tools.md)
- [tools/write_to_file/tools.md](tools/write_to_file/tools.md)

---

> 文档与代码一致性按 `doc/` 各分册核对；实现以仓库源码为准。
