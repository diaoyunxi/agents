"""System 提示词组装：内置规则 + 工具 tools.md + 技能文档 + MCP 说明。"""

from __future__ import annotations

import config
import skill_loader
from tools import loader as tool_loader

CORE_RULES = """你是一个运行在本地工作区里的智能体 Agent，可以通过正文调用工具来读写文件、执行命令，真正帮用户完成工作。

# 工具调用协议（非常重要）

本项目不使用 OpenAI 风格的 tools/function 字段。只能通过正文调用工具，规则如下：

1. 每次调用工具，在正文中直接输出一个 JSON 对象，字段固定为：
   - tool：工具名，必须是下面工具清单中的名称之一
   - arguments：参数字典，键名与该工具文档中的参数名完全一致
   - thought（可选）：调用前的一句话说明
2. 一次回复中允许输出多个 JSON 对象，它们会被依次执行；还需要继续操作时就继续输出。
3. 如果只是想讲解或展示内容（不是调用工具），正文中的所有花括号都必须转义，即写成斜杠加左花括号、斜杠加右花括号。
4. 允许在工具调用 JSON 之前先输出一段描述性文字（例如「我先查看目录结构：」），会展示给用户。
5. 不要把 JSON 放进 Markdown 代码块，不要注释、不要尾逗号，必须是严格合法的 JSON。
6. 只传必要的参数，不要臆造参数名；参数非法时工具会返回错误，请据错误修正后重试。
7. 拿到工具结果后继续判断下一步：是否还需要其它工具，或可以给出最终答复。
8. 任务完成时用简洁的中文 Markdown 总结做了什么、改了哪些文件。
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
    return "\n".join(lines)


def _mcp_section() -> str:
    try:
        from mcp_manager import mcp_prompt_section
        return mcp_prompt_section()
    except Exception:
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
