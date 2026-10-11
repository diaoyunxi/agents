# Agents · 本地智能体工作台

一个用 Python 后端驱动的本地 AI Agent。Web 端只负责展示，所有真实能力（AI 调用、工具执行、MCP、配置、文件读写）都实现在后端。

- 监听端口：`6573`（可在 `config.json` 中修改）
- 访问地址：<http://localhost:6573/>
- 默认账号：`root` / `root`（首次登录后可在设置页修改）

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

启动后会自动打开浏览器；未配置 AI 时会进入新手引导：

1. 配置 AI 的 Base URL
2. 填写 API Key
3. 自动获取可用模型
4. 选择默认模型
5. 设置工具调用限制

## 目录结构

```
agents/
├─ main.py              启动入口（读取 config.json 中的 host/port）
├─ app.py               FastAPI 后端：认证 / 配置 / 模型 / 工具 / MCP / SSE 对话
├─ agent_runtime.py     对话运行时：模型输出 -> 解析工具调用 -> 执行 -> 回灌
├─ ai_client.py         OpenAI 兼容客户端（多提供商、模型列表、流式对话）
├─ tool_parser.py       正文 JSON 工具调用解析（含转义处理）
├─ prompt_builder.py    System 提示词组装
├─ mcp_manager.py       MCP 服务器接入与工具注册
├─ common.py            工作区沙箱、文件变更与 diff 采集
├─ config.py            config.json 读写与变更热加载
├─ git_update.py        自更新检查：git status / fetch，比较本地与远端提交
├─ updater.py           独立的自更新重启器（负责拉代码并重新拉起服务）
├─ skill_loader.py      skills/ 目录加载
├─ tools/               工具目录：每个工具一个文件夹
│  ├─ read_file/  ├─ write_file/  ├─ edit_file/
│  ├─ list_dir/  ├─ search_files/  ├─ run_shell/
│  └─ stop/                 结束信号工具（模型显式结束本次任务）
├─ skills/              技能目录：一个技能一个 md 文件
├─ web/                 纯展示前端（登录引导 / 对话 / 设置）
└─ config.json          所有配置
```

## 界面

前端为纯展示层，采用 Anthropic 品牌规范：墨色 `#141413` / 米白 `#faf9f5` / 中灰 `#b0aea5` / 浅灰 `#e8e6dc`，强调色为橙 `#d97757`、蓝 `#6a9bcc`、绿 `#788c5d`；标题使用 Poppins（回退 Arial），正文使用 Lora（回退 Georgia）。界面不使用任何表情符号，状态一律以文字标签与颜色区分。

- `/` 登录与新手引导
- `/chat` 对话：中间逐轮展示思考、输出、工具调用全过程；右侧面板汇总文件变更；输入框上方可为每轮对话指定工作区（留空使用默认工作区）
- `/settings` 设置：左侧导航切换 AI 提供商、模型与默认、工具与限制、MCP、技能与提示词、账号

## 自动更新

每次打开页面时，后端都会执行一次 `git status` 并对比远端分支（`git fetch` + `rev-list`）。若发现新提交，页面左下角出现提示条，可展开查看提交列表，点击「立即更新」即可完成更新与重启。

1. 后端以**分离进程**方式启动 `updater.py`，随后让 Web 服务进程自行退出；
2. `updater.py` 等待旧进程完全退出后执行 `git fetch` + `git merge --ff-only`，再拉起新的 `python main.py`；
3. 前端轮询 `/api/health`，服务恢复后自动刷新页面（登录状态因会话落盘而得以保留）。

关键在于更新器是**独立进程**：Python 启动时就把源码编译进内存，之后不再依赖磁盘文件，因此即使 git 把磁盘上的源码（包括 `updater.py` 自己）替换或删除，它依然能执行完「拉代码 → 重启服务」的闭环。若网络不通，拉取会快速失败，并按原代码照常重启，保证服务可用。

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

## 添加一个工具

在 `tools/` 下新建以工具名命名的文件夹，放入 `tools.py` 与 `tools.md`（文件名不区分大小写），目录内可放任意其它文件（辅助模块会被自动导入）：

```
tools/my_tool/
├─ tools.py     # 必须提供 run(**kwargs)，可选 NAME / DESCRIPTION / PARAMETERS / DANGEROUS
└─ tools.md     # 自然语言说明（作用、参数、返回、注意事项），会整篇嵌入 system 提示词
```

`tools.py` 示例：

```python
NAME = "my_tool"
DESCRIPTION = "一句话说明"
PARAMETERS = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "参数说明"}},
    "required": ["path"],
}

def run(path: str) -> str:
    return "结果"
```

返回 `dict` 时可用 `{"ok": False, "output": "错误原因"}` 告知模型失败原因。

## 添加一个技能

在 `skills/` 下放一个 md 文件，文件名即技能名，内容会整篇嵌入 system 提示词。支持可选的 front-matter（`name` / `description` / `when_to_use`）。

## 工具调用协议

请求模型时**不携带 tools 字段**，而是在 system 提示词中要求模型通过正文输出 JSON：

```json
{"tool": "read_file", "arguments": {"path": "README.md"}, "thought": "读取说明文件"}
```

- 一次回复允许输出多个 JSON，后端会依次执行
- 非工具调用的花括号必须转义为 `/{` 与 `/}`，后端会自动还原
- 允许在 JSON 之前输出描述性文字

## 结束协议

模型必须在任务真正完成时调用内置工具 `stop` 显式结束本次任务（`stop` 不受调用次数与禁用列表约束，且不计入次数）：

```
{"tool": "stop", "arguments": {"reason": "已完成 README 更新"}}
```

若某一轮模型没有调用任何工具，运行时会回灌一条指令要求继续推进；连续 3 轮空转才会强制结束，避免死循环。

## MCP

在设置页「MCP 服务器」中填写 `npx` 之类的命令与参数，保存后点击「刷新连接」。连接成功后其工具会以 `mcp__服务器名__工具名` 的形式自动注册并写入提示词。需要先安装 MCP SDK：`pip install mcp`。

## 安全说明

- 密码登录后才可访问 API，密码以明文存于本机 `config.json`，请勿提交到版本库
- 所有文件读写都被限制在 `server.workspace` 之内，越界路径会被拒绝
- `run_shell` 属于高风险工具，可在设置页的「禁用列表」中关闭

