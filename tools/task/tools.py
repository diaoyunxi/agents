"""启动子代理执行任务（内置 code-explorer：只读代码库探索）。"""

from __future__ import annotations

import json
import uuid
from typing import Any

NAME = "task"
DESCRIPTION = "启动一个子代理独立执行任务并返回结果；内置 code-explorer（只读探索代码库，定位实现、梳理调用链）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "subagent_type": {
            "type": "string",
            "description": "子代理类型，目前内置 code-explorer",
            "enum": ["code-explorer"],
        },
        "description": {"type": "string", "description": "一句话说明这次子代理任务是什么（3-5 词）"},
        "prompt": {"type": "string", "description": "给子代理的完整任务指令：要查什么、返回什么格式"},
    },
    "required": ["description", "prompt"],
}

SUBAGENTS: dict[str, dict[str, Any]] = {
    "code-explorer": {
        "role": "代码库探索专家",
        "tools": ["list_dir", "search_file", "search_content", "read_file"],
        "max_rounds": 12,
        "max_calls": 30,
        "instructions": (
            "你是只读的代码探索子代理：不能修改任何文件、不能执行命令。"
            "请通过 list_dir / search_file / search_content / read_file 收集证据，"
            "回答中给出关键结论与 `文件路径:行号` 证据，最后直接给出结论（不要再调用 stop 之外的收尾动作）。"
        ),
    }
}

SYSTEM_TEMPLATE = """你是 {role}，一个由主代理启动的子代理，工作区为：

{workspace}

{instructions}

# 工具调用协议

优先使用 OpenAI function calling 直接调用上面列出的只读工具；一次回复可多次调用。
不支持函数调用时，也可在正文输出严格合法 JSON：{{"tool": "工具名", "arguments": {{...}}}}。

# 输出要求

- 用中文作答，结论先行，再列证据（`路径:行号`）。
- 只汇报与任务相关的发现，不要堆砌无关文件清单。
- 收集到足够信息后直接给出最终答复，结束工具调用。"""


def _subagent_tools(allowed: list[str]) -> list[dict]:
    """读取注册表里子代理可用的只读工具，转成 function calling schema。"""

    import function_tools
    from tools import loader as tool_loader

    items = [t for t in tool_loader.list_tools() if t["name"] in allowed]
    return function_tools.build_function_tools(items)


def _subagent_prompt(agent: dict, description: str, prompt: str) -> str:
    from config import workspace_dir

    docs = []
    from tools import loader as tool_loader

    for name in agent["tools"]:
        item = tool_loader.get_tool(name)
        if item:
            docs.append(f"### 工具 `{name}` —— {item.get('description', '')}\n{item.get('doc', '')}")
    return SYSTEM_TEMPLATE.format(
        role=agent["role"],
        workspace=str(workspace_dir()),
        instructions=agent["instructions"],
    ) + "\n\n# 可用工具\n\n" + ("\n\n".join(docs) if docs else "（无）") \
        + f"\n\n# 本次任务\n\n{description}\n\n{prompt}"


async def _run_loop(agent: dict, system: str, task_text: str) -> str:
    import ai_client
    import config
    import tool_parser
    from tools import loader as tool_loader

    providers = config.get("providers", []) or []
    if not providers:
        return "（子代理无法启动：尚未配置任何 AI 提供商）"
    pid = config.get("ai.active_provider_id", "")
    provider = next((p for p in providers if p.get("id") == pid), None) or providers[0]
    model = config.get("ai.active_model", "") or provider.get("default_model", "")
    if not model:
        return "（子代理无法启动：尚未选择模型）"

    tools = _subagent_tools(agent["tools"])
    messages: list[dict] = [{"role": "system", "content": system},
                            {"role": "user", "content": task_text}]
    final = ""
    calls_used = 0

    for _ in range(agent["max_rounds"]):
        try:
            content, _reasoning, tool_calls = await ai_client.chat(provider, model, messages, tools=tools or None)
        except Exception as exc:  # noqa: BLE001
            return f"（子代理模型调用失败: {exc}）" + (f"\n\n已获得的阶段性结论：\n{final}" if final else "")

        calls: list[dict] = []
        for tc in tool_calls or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, ValueError):
                args = {}
            calls.append({"id": tc.get("id") or "call_" + uuid.uuid4().hex[:10],
                          "name": fn.get("name", ""), "arguments": args,
                          "raw": fn.get("arguments") or "{}"})
        if not calls:
            for seg in tool_parser.parse_segments(content or ""):
                if seg["type"] == "tool_call":
                    calls.append({"id": "call_" + uuid.uuid4().hex[:10],
                                  "name": seg["tool"], "arguments": seg["arguments"], "raw": ""})

        if not calls:
            return content or final or "（子代理未产生输出）"

        messages.append({
            "role": "assistant",
            "content": content or None,
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["raw"] or "{}"}}
                           for c in calls],
        })
        for call in calls:
            name = call["name"]
            if name not in agent["tools"]:
                output = f"错误：子代理 `{agent['role']}` 无权使用工具 `{name}`（可用: {', '.join(agent['tools'])}）"
            else:
                calls_used += 1
                outcome = await tool_loader.call_tool(name, call["arguments"])
                output = str(outcome.get("output", ""))[:12000]
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
            if content:
                final = content
            if calls_used >= agent["max_calls"]:
                messages.append({"role": "user", "content":
                                 "（已达工具调用上限，请基于已有信息立即给出最终结论）"})
                try:
                    content2, _r, _tc = await ai_client.chat(provider, model, messages)
                    return content2 or final or "（子代理达到调用上限且未给出结论）"
                except Exception as exc:  # noqa: BLE001
                    return f"（子代理收尾调用失败: {exc}）\n\n阶段性结论：\n{final}"
    return final or "（子代理达到轮数上限，未给出最终结论）"


async def run(description: str, prompt: str, subagent_type: str = "code-explorer") -> dict:
    agent = SUBAGENTS.get((subagent_type or "").strip())
    if agent is None:
        return {"ok": False, "output":
                f"未知子代理类型: {subagent_type}（当前内置: {', '.join(SUBAGENTS)}）"}
    if not (description or "").strip() or not (prompt or "").strip():
        return {"ok": False, "output": "description 与 prompt 均不能为空"}

    system = _subagent_prompt(agent, description.strip(), prompt.strip())
    final = await _run_loop(agent, system, f"{description.strip()}\n\n{prompt.strip()}")
    return {"output": f"[子代理 {subagent_type} 结果]\n{final}"}


__all__ = ["run", "SUBAGENTS", "NAME", "DESCRIPTION", "PARAMETERS"]
