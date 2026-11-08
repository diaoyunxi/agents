> [← 返回文档目录](../README.md) ｜ 本分册由 `README.md` 的「配置说明（config.json）」章节拆分而来。

## 配置说明（config.json）

程序启动时读取，运行期间被外部修改会自动热加载（2 秒内生效），通过设置页修改会立即写盘并备份到 `.config_backups/`。

| 字段 | 说明 |
| --- | --- |
| `server` | `host`、`port`、`workspace`（默认工作区根目录；对话页可为每轮对话临时覆盖） |
| `auth` | `enabled`、`username`、`password`、`setup_done` |
| `providers` | 多个 AI 提供商：`name`、`base_url`、`api_key`、`models`、`default_model`、`headers` |
| `ai` | `active_provider_id`、`active_model`、`max_tokens`、`temperature`、`timeout` |
| `tool_limits` | 工具调用限制：`enabled`、`max_calls_per_round`、`max_total_calls`、`max_rounds`、`allowed_tools`、`denied_tools`、`require_confirmation` |
| `mcp_servers` | MCP 服务器：`name`、`command`、`args`、`env`、`cwd`、`enabled` |
| `web_search` | 联网搜索：`provider`（duckduckgo/brave/tavily）、`api_key`、`max_results`、`timeout` |
