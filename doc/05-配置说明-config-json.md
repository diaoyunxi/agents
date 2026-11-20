> [← 返回文档目录](../README.md) ｜ 本分册由 `README.md` 的「配置说明（config.json）」章节拆分而来。

## 配置说明（config.json）

程序启动时读取，运行期间被外部修改会自动热加载（2 秒内生效），通过设置页修改会立即写盘并备份到 `.config_backups/`。

| 字段 | 说明 |
| --- | --- |
| `server` | `host`、`port`、`workspace`（默认工作区根目录；对话页可为每轮对话临时覆盖） |
| `auth` | `enabled`、`username`、`password`、`setup_done` |
| `providers` | 多个 AI 提供商：`name`、`base_url`、`api_key`、`models`、`default_model`、`headers`、`model_type_overrides`（`{模型ID: 类型}`，手动覆盖某模型的类型识别结果；类型缺省按模型 ID 自动识别） |
| `ai` | `active_provider_id`、`active_model`、`max_tokens`、`temperature`、`timeout` |
| `tool_limits` | 工具调用限制：`enabled`、`max_calls_per_round`、`max_total_calls`、`max_rounds`、`allowed_tools`、`denied_tools`、`require_confirmation` |
| `tool_toggles` | 工具允许开关：`{工具名: true/false}`，缺省视为启用；`false` 时该工具不出现在提示词和 function calling schema 中，调用会被拒绝。MCP 工具同样适用（键为 `mcp__服务器名__工具名`） |
| `custom` | 自定义配置：任意键值字典，可被工具代码通过 `loader.get_custom_config()` 读取，用于工具行为参数（如默认大小、超时、密钥等） |
| `custom_prompts` | 用户自定义 Prompt 列表：`id`、`name`、`content`、`enabled`；已启用项按顺序追加到 System Prompt，缺省兼容为空列表 |
| `mcp_servers` | MCP 服务器：`name`、`command`、`args`、`env`、`cwd`、`enabled` |
| `web_search` | 联网搜索：`provider`（duckduckgo/brave/tavily）、`api_key`、`max_results`、`timeout` |

### 模型类型（model_type）

模型列表（`provider.models`）里每一项带一个 `type` 字段，是程序按「模型 ID + 提供商类型」自动识别出的能力类型。识别命中后，请求时走不同的 API 端点与请求体：

| 类型 | 请求端点 | 说明 |
| --- | --- | --- |
| `text_generation` / `translation` / `text_classification` | `POST /chat/completions` | 对话/生成格式；翻译可只给 `{text, source, target}` |
| `text_embedding` | `POST /embeddings` | 文本 → 向量 |
| `text_to_image` | `POST /images/generations` | 文本 → 图片（base64 / URL） |
| `image_to_text` / `image_classification` | `POST /chat/completions`（多模态 `image_url`） | 图片 + 问题 |
| `automatic_speech_recognition` | `POST /audio/transcriptions`（multipart） | 音频 → 文本 |
| `text_to_speech` | `POST /audio/speech` | 文本 → 音频 |
| `voice_activity_detection` | 透传 provider 自定义端点 | 非标准，需显式配置 |

- 自动识别规则见 `ai_client.py` 的 `_MODEL_TYPE_RULES`（正则匹配模型 ID，先命中先用；未命中默认 `text_generation`）。
- 若识别不准，可在 `provider.model_type_overrides` 里按模型 ID 手动指定类型，或点设置页模型列表中的类型徽章修改。
- 非对话类型的一次推理调用入口：`POST /api/providers/{pid}/invoke`（`ai_client.model_inference` 按类型分发）。
- 针对某模型按类型做连通性探测：`POST /api/providers/{pid}/test`，body 带 `{model, model_type?}`。
