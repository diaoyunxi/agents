"""System 提示词组装：内置规则 + 工具 tools.md + 技能文档 + MCP 说明。"""

from __future__ import annotations

import config
from tools import loader as tool_loader
import skill_loader

CORE_RULES = """你是一个运行在本地工作区里的智能体 Agent，可以通过调用工具来读写文件、执行命令，真正帮用户完成工作。

# 工具调用协议（OpenAI function calling）

本项目的工具通过 OpenAI 标准的 function calling 提供：请求里会带上 `tools` 字段，
每个工具都是一个函数，附带参数 JSON Schema。请优先使用函数调用，而不是在正文里手写 JSON：

1. 需要执行某个操作时，直接调用对应的函数；参数必须严格符合该函数定义的 JSON Schema
   （键名、类型都要一致，不要臆造参数）。
2. 一次回复里可以多次调用函数，它们会被依次执行；还需要继续操作就继续调用。
3. 调用函数之前可以先输出一段说明性文字（例如「我先查看目录结构：」），会展示给用户。
4. 拿到函数结果后继续判断：是否还需要其它操作，或已可以给出最终答复。
5. 不需要调用工具时（例如只是回答问题），正常用正文回复即可，不要编造函数调用。
6. 参数非法或调用失败时工具会返回错误，请据错误修正后重试。
7. **结束协议（强制）**：任务真正完成时，调用函数 `stop`（可带 `reason` 说明）显式结束。
   - 只要还有可推进的工作就继续调用工具，不要提前调用 `stop`；
   - 任何一轮都不调用函数（含 `stop`）会被运行时判定为「未完成」并要求你继续推进；
   - `stop` 必须是你本轮的最后一次调用，调用后不要再输出其它函数调用。
8. 任务完成时用简洁的中文 Markdown 总结做了什么、改了哪些文件。

（兼容说明：极少数不支持 function calling 的模型，可在正文直接输出严格合法的
 JSON 对象 `{"tool":"工具名","arguments":{...}}` 来调用工具；但首选始终是上面的函数调用。）
"""

def _limits_section() -> str:
    limits = config.get("tool_limits", {}) or {}
    lines = ["# 工具调用限制"]
    if not limits.get("enabled", True):
        lines.append("- 当前未启用调用限制，可自由调用工具，但仍需注意安全。")
        return "\n".join(lines)
    lines.append("- 单轮最多调用 {0} 次工具".format(limits.get("max_calls_per_round", 10)))
    lines.append("- 整个会话最多调用 {0} 次工具".format(limits.get("max_total_calls", 60)))
    lines.append("- 最多进行 {0} 轮工具交互".format(limits.get("max_rounds", 25)))
    allowed = limits.get("allowed_tools") or []
    denied = limits.get("denied_tools") or []
    if allowed:
        lines.append("- 仅允许调用：{0}".format(", ".join(allowed)))
    if denied:
        lines.append("- 禁止调用：{0}（调用会被拒绝并计入次数）".format(", ".join(denied)))
    confirm = limits.get("require_confirmation") or []
    if confirm:
        lines.append("- 以下工具需先征得用户确认：{0}".format(", ".join(confirm)))
    lines.append("- 工具 `stop` 为结束信号，不受以上允许/禁用列表与次数上限约束，始终可用。")
    return "\n".join(lines)


def _mcp_section() -> str:
    try:
        from mcp_manager import mcp_prompt_section
        return mcp_prompt_section()
    except Exception:  # noqa: BLE001
        return ""


def build_system_prompt(extra: str = "") -> str:
    """组装完整 system 提示词。"""

    from common import workspace_dir

    parts = [CORE_RULES]
    parts.append("# 工作区信息\n- 根目录：{0}\n- 当前时间：{1}".format(
        workspace_dir(), __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    tool_docs = tool_loader.build_prompt_section()
    parts.append("# 可用工具\n\n以下是本项目内置工具的完整说明（每个工具的目录内都有一个同名 md 文档，内容已全部包含在这里）：\n\n" + tool_docs
                 if tool_docs else "# 可用工具\n\n（当前没有内置工具）")

    mcp = _mcp_section()
    if mcp:
        parts.append(mcp)

    skills = skill_loader.build_prompt_section()
    if skills:
        parts.append(skills)

    parts.append(_limits_section())
    parts.append("# 输出风格\n- 默认使用中文，结构清晰，善用 Markdown 小标题、列表与代码块。\n- 引用代码时标明文件路径与关键行。\n- 不要输出与任务无关的客套话。")
    if extra.strip():
        parts.append(extra.strip())
    return "\n\n".join(p for p in parts if p)


def build_user_context() -> str:
    from common import workspace_dir
    root = workspace_dir()
    try:
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in root.iterdir())
    except OSError:
        entries = []
    listing = "\n".join(entries[:80]) or "(空)"
    return "当前工作区根目录内容：\n" + listing


def refresh() -> str:
    tool_loader.refresh()
    return build_system_prompt()
