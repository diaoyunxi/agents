#!/usr/bin/env python3
"""把内置工具 / MCP 工具 / 控制工具转换为 OpenAI function calling（tools 字段）所需 schema。

与 tool_parser 的正文调用协议互不排斥：运行时优先使用函数调用，
个别不支持 function calling 的模型仍可走正文 JSON（见 agent_runtime 的兼容分支）。
"""

from __future__ import annotations

from typing import Any


# 控制信号：模型调用它即表示任务结束。在 function calling 范式下它本身也是一个函数，
# 运行时仍按 stop_task 标记识别并停止后续交互。
STOP_FUNCTION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "stop",
        "description": (
            "信号工具：AI 明确请求结束当前任务（不执行任何副作用）。"
            "仅当任务真正完成、没有更多可推进的工作时才调用；"
            "调用后本轮交互结束，因此必须是本轮最后一次调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "可选，停止原因 / 一句话总结，会回显给用户",
                }
            },
            "required": [],
        },
    },
}


def tool_to_function(tool: dict[str, Any]) -> dict[str, Any]:
    """单个工具定义 -> OpenAI function 对象。"""

    params = tool.get("parameters") or {"type": "object", "properties": {}}
    if not isinstance(params, dict):
        params = {"type": "object", "properties": {}}
    params = dict(params)
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    return {
        "type": "function",
        "function": {
            "name": str(tool.get("name", "")),
            "description": (tool.get("description") or "").strip(),
            "parameters": params,
        },
    }


def build_function_tools(
    builtin: list[dict] | None = None,
    mcp: list[dict] | None = None,
    extra: list[dict] | None = None,
) -> list[dict]:
    """组装完整 tools 列表。

    builtin: tool_loader.list_tools() 的结果
    mcp:     mcp_manager.list_all_tools() 的结果
    extra:   额外函数（如 STOP_FUNCTION 控制信号）
    """

    out: list[dict] = []
    for t in (builtin or []):
        out.append(tool_to_function(t))
    for t in (mcp or []):
        out.append(tool_to_function({
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "parameters": t.get("parameters") or {"type": "object", "properties": {}},
        }))
    for t in (extra or []):
        out.append(t)
    return out
