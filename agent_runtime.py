#!/usr/bin/env python3
"""对话运行时：模型输出 -> 解析工具调用 -> 执行工具 -> 回灌结果。

以异步生成器产出事件，供后端 SSE 推送给前端：
thinking / delta（思考与正文增量）、message（本轮结构化片段）、
tool_start / tool_end（工具调用）、changes（文件变更）、limit / error / end。
"""

from __future__ import annotations

import json
import time
import uuid

import ai_client
import config
import function_tools
import mcp_manager
import prompt_builder
import tool_parser
from common import ChangeCollector
from tools import loader as tool_loader

# 控制信号工具：模型调用它即表示「本次任务到此结束」
STOP_TOOL = "stop"

# 模型未调用任何工具时的续推提示；连续触发到上限则强制结束，避免死循环
IDLE_PUSH_LIMIT = 3
IDLE_PUSH_TEMPLATE = (
    "（运行时提醒）你这一轮没有调用任何工具，任务尚未被标记为结束。\n"
    "请继续推进：如果还有工作没做，就调用相应工具去做；如果确实已经完成，"
    "请调用工具 `{stop}` 来显式结束（可带参数 reason 说明理由）。"
).format(stop=STOP_TOOL)
IDLE_GIVE_UP = "已连续 {0} 轮未调用任何工具，本次任务到此结束。"

def resolve_provider(provider_id: str = "", model: str = "") -> tuple:
    """返回 (provider, model)；请求未指定时回落到 config 中的当前选择。"""
    providers = config.get("providers", []) or []
    if not providers:
        raise ValueError("尚未配置任何 AI 提供商，请先到设置页完成配置。")
    pid = provider_id or config.get("ai.active_provider_id", "")
    provider = next((p for p in providers if p.get("id") == pid), None) or providers[0]
    chosen = model or config.get("ai.active_model", "") or provider.get("default_model", "")
    if not chosen:
        raise ValueError("尚未选择模型，请先到设置页获取并选择默认模型。")
    return provider, chosen


def _limits() -> dict:
    return config.get("tool_limits", {}) or {}


def _check_allowed(name: str, limits: dict) -> str:
    """返回空串表示允许，否则返回拒绝原因。`stop` 是控制信号，永远放行。"""
    if name == STOP_TOOL:
        return ""
    if not limits.get("enabled", True):
        return ""
    allowed = limits.get("allowed_tools") or []
    if allowed and name not in allowed:
        return "工具 `{0}` 不在允许列表中（允许: {1}）".format(name, ", ".join(allowed))
    denied = limits.get("denied_tools") or []
    if name in denied:
        return "工具 `{0}` 已被禁用".format(name)
    return ""


async def _dispatch(name: str, arguments: dict) -> dict:
    if name.startswith("mcp__"):
        return await mcp_manager.call_tool(name, arguments)
    return await tool_loader.call_tool(name, arguments)


PARSE_RETRY_LIMIT = 3

PARSE_ERROR_GUIDE = (
    "请重新输出一个严格合法的 JSON 对象：\n"
    "  1) 字符串里的换行必须写成 \\n，制表符写成 \\t；\n"
    "  2) 只能用半角双引号 \"，不要用中文引号「」或 “ ”；\n"
    "  3) 内容里要出现的双引号必须写成 \\\"，不要直接输出裸引号；\n"
    "  4) 不要有尾逗号、注释，也不要用 Markdown 代码块包裹；\n"
    "  5) content 再长也必须保持单行 JSON 字符串。"
)


def _format_results(results: list) -> str:
    lines = ["[工具执行结果]"]
    has_parse_error = False
    for item in results:
        flag = "成功" if item.get("ok") else "失败"
        if item.get("parse_error"):
            has_parse_error = True
            flag = "未执行（JSON 解析失败）"
        lines.append("- 工具 `{0}`：{1}".format(item["tool"], flag))
        lines.append("  参数: {0}".format(json.dumps(item.get("arguments", {}), ensure_ascii=False)[:500]))
        lines.append("  输出: {0}".format(str(item.get("output", ""))[:6000]))
    if has_parse_error:
        lines.append("注意：上述工具调用因为 JSON 不合法而**没有被执行**，请修正格式后重发。")
        lines.append(PARSE_ERROR_GUIDE)
    lines.append("请根据以上结果决定下一步（继续调用工具，或给出最终答复）。")
    if any(item.get("stop_task") for item in results):
        lines.append("你已调用 `{0}`，本轮交互到此结束，不会再回灌新的指令。".format(STOP_TOOL))
    return "\n".join(lines)


async def run_chat(user_input, history=None, provider_id="", model=""):
    """执行一轮完整对话，产出事件字典流。"""
    history = history or []
    limits = _limits()
    enabled = limits.get("enabled", True)
    max_rounds = int(limits.get("max_rounds", 25)) if enabled else 200
    max_total = int(limits.get("max_total_calls", 60)) if enabled else 100000
    max_per_round = int(limits.get("max_calls_per_round", 10)) if enabled else 1000

    provider, chosen_model = resolve_provider(provider_id, model)
    await mcp_manager.refresh_prompt()
    system = prompt_builder.build_system_prompt() + "\n\n" + prompt_builder.build_user_context()

    messages = [{"role": "system", "content": system}]
    for item in history:
        role = item.get("role")
        if role in ("user", "assistant") and item.get("content"):
            messages.append({"role": role, "content": item["content"]})
    messages.append({"role": "user", "content": user_input})

    started = time.time()
    yield {
        "event": "start",
        "session_id": uuid.uuid4().hex[:12],
        "provider": provider.get("name") or provider.get("id"),
        "model": chosen_model,
        "workspace": str(config.workspace_dir()),
        "limits": {
            "max_rounds": max_rounds,
            "max_total_calls": max_total,
            "max_calls_per_round": max_per_round,
        },
    }

    with ChangeCollector() as collector:
        total_calls = 0
        parse_streak = 0
        idle_streak = 0
        stop_reason = "completed"
        stop_detail = ""
        # 构建 OpenAI function calling 所需的 tools schema（失败则降级为正文调用）
        tools = []
        if config.get("ai.use_function_calling", True):
            try:
                builtin = tool_loader.list_tools()
                mcp_tools = await mcp_manager.list_all_tools()
                tools = function_tools.build_function_tools(builtin, mcp_tools, [function_tools.STOP_FUNCTION])
            except Exception as exc:  # noqa: BLE001
                print("[runtime] 构建函数工具失败，降级为正文调用: " + str(exc))
                tools = []

        for round_index in range(1, max_rounds + 1):
            yield {"event": "round", "index": round_index}
            content = ""
            reasoning = ""
            tool_calls = []
            stream_error = ""
            try:
                async for item in ai_client.stream_chat(provider, chosen_model, messages, tools=tools or None):
                    kind = item.get("type")
                    chunk = str(item.get("content") or "")
                    if kind == "thinking_delta":
                        reasoning += chunk
                        yield {"event": "thinking", "content": chunk, "delta": True}
                    elif kind == "content_delta":
                        content += chunk
                        yield {"event": "delta", "content": chunk}
                    elif kind == "tool_calls":
                        tool_calls = item.get("calls") or []
            except Exception as exc:  # noqa: BLE001
                stream_error = str(exc)
                try:
                    content, reasoning, tool_calls = await ai_client.chat(
                        provider, chosen_model, messages, tools=tools or None)
                except Exception as exc2:  # noqa: BLE001
                    yield {"event": "error", "message": str(exc2) or stream_error}
                    stop_reason = "error"
                    break
                yield {"event": "delta", "content": content}
                yield {"event": "fallback", "message": "流式不可用，已回退为一次性返回: " + stream_error}

            if reasoning:
                yield {"event": "thinking_done", "content": reasoning}

            # 解析原生（OpenAI function calling）工具调用
            native_calls = []
            for tc in (tool_calls or []):
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or ""
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                except (json.JSONDecodeError, ValueError):
                    args = {"__raw__": raw_args}
                native_calls.append({
                    "id": tc.get("id") or "call_{0}".format(uuid.uuid4().hex[:12]),
                    "name": name,
                    "arguments": args,
                    "raw_args": raw_args,
                })

            segments = tool_parser.parse_segments(content)
            inline_calls = [seg for seg in segments if seg["type"] == "tool_call"]
            broken = [seg for seg in segments if seg["type"] == "tool_call_error"]
            for nc in native_calls:
                segments.append({"type": "tool_call", "tool": nc["name"],
                                 "arguments": nc["arguments"], "thought": "", "raw": nc["raw_args"]})

            yield {
                "event": "message",
                "round": round_index,
                "segments": segments,
                "tool_calls": len(native_calls) + len(inline_calls),
                "parse_errors": len(broken),
                "raw": content,
            }

            # ---- 路径一：原生 function calling ----
            if native_calls:
                idle_streak = 0
                messages.append({
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {"id": nc["id"], "type": "function",
                         "function": {"name": nc["name"], "arguments": nc["raw_args"]}}
                        for nc in native_calls
                    ],
                })
                tool_messages = []
                round_calls = 0
                stopped = False
                for nc in native_calls:
                    name = nc["name"]
                    args = nc["arguments"]
                    deny = _check_allowed(name, limits)
                    if deny:
                        tool_messages.append({"role": "tool", "tool_call_id": nc["id"], "content": deny})
                        yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": deny}
                        continue
                    is_stop = name == STOP_TOOL
                    if not is_stop:
                        if total_calls >= max_total:
                            msg = "已达到本会话工具调用总上限 {0} 次，停止调用并给出总结。".format(max_total)
                            tool_messages.append({"role": "tool", "tool_call_id": nc["id"], "content": msg})
                            yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": msg}
                            continue
                        if round_calls >= max_per_round:
                            msg = "本轮工具调用次数已达上限 {0} 次。".format(max_per_round)
                            tool_messages.append({"role": "tool", "tool_call_id": nc["id"], "content": msg})
                            yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": msg}
                            continue
                        total_calls += 1
                        round_calls += 1
                    yield {"event": "tool_start", "tool": name, "arguments": args, "thought": ""}
                    outcome = await _dispatch(name, args)
                    outcome = dict(outcome)
                    outcome["tool"] = name
                    outcome["arguments"] = args
                    yield {
                        "event": "tool_end",
                        "tool": name,
                        "arguments": args,
                        "ok": bool(outcome.get("ok", True)),
                        "output": str(outcome.get("output", ""))[:20000],
                    }
                    yield {"event": "changes", "changes": collector.snapshot()}
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": nc["id"],
                        "content": str(outcome.get("output", ""))[:20000],
                    })
                    if outcome.get("stop_task"):
                        stopped = True
                        stop_detail = str(args.get("reason") or outcome.get("reason") or "").strip()
                        break
                messages.extend(tool_messages)
                yield {"event": "round_done", "index": round_index, "calls": total_calls,
                       "elapsed_ms": int((time.time() - started) * 1000)}
                if stopped:
                    stop_reason = "stopped"
                    yield {"event": "stopped", "reason": stop_detail,
                           "message": "模型已调用 `stop` 结束本次任务。" + (" 说明: " + stop_detail if stop_detail else "")}
                    break
                continue

            # ---- 路径二：正文调用（兼容模型未走 function calling） ----
            messages.append({"role": "assistant", "content": content})

            if not inline_calls and not broken:
                idle_streak += 1
                if idle_streak >= IDLE_PUSH_LIMIT:
                    stop_reason = "idle"
                    stop_detail = IDLE_GIVE_UP.format(idle_streak)
                    yield {"event": "limit", "message": stop_detail}
                    break
                messages.append({"role": "user", "content": IDLE_PUSH_TEMPLATE})
                yield {"event": "round_done", "index": round_index, "calls": 0,
                       "elapsed_ms": int((time.time() - started) * 1000)}
                continue
            idle_streak = 0

            results = []

            # 形似工具调用但 JSON 非法：回灌错误，让模型修正后重试
            for seg in broken:
                name = seg.get("tool") or "(未识别)"
                output = "{0}\n\n{1}".format(seg["error"], PARSE_ERROR_GUIDE)
                results.append({"tool": name, "arguments": {}, "ok": False,
                                "output": output, "parse_error": True})
                yield {"event": "tool_start", "tool": name, "arguments": {},
                       "thought": "JSON 解析失败，未执行"}
                yield {"event": "parse_error", "tool": name, "error": seg["error"],
                       "raw": seg["raw"][:2000]}
                yield {"event": "tool_end", "tool": name, "arguments": {}, "ok": False,
                       "output": output}

            parse_streak = parse_streak + 1 if (broken and not inline_calls) else 0
            if parse_streak >= PARSE_RETRY_LIMIT:
                yield {"event": "limit",
                       "message": "连续 {0} 轮工具调用 JSON 无法解析，已停止本轮，请检查模型输出格式。".format(parse_streak)}
                stop_reason = "parse_failed"
                break

            round_calls = 0
            stopped = False
            for call in inline_calls:
                name = call["tool"]
                args = call["arguments"]
                deny = _check_allowed(name, limits)
                if deny:
                    results.append({"tool": name, "arguments": args, "ok": False, "output": deny})
                    yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": deny}
                    continue
                is_stop = name == STOP_TOOL
                if not is_stop:
                    if total_calls >= max_total:
                        msg = "已达到本会话工具调用总上限 {0} 次，停止调用并给出总结。".format(max_total)
                        results.append({"tool": name, "arguments": args, "ok": False, "output": msg})
                        yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": msg}
                        continue
                    if round_calls >= max_per_round:
                        msg = "本轮工具调用次数已达上限 {0} 次。".format(max_per_round)
                        results.append({"tool": name, "arguments": args, "ok": False, "output": msg})
                        yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": msg}
                        continue
                    total_calls += 1
                    round_calls += 1
                yield {"event": "tool_start", "tool": name, "arguments": args, "thought": call.get("thought", "")}
                outcome = await _dispatch(name, args)
                outcome = dict(outcome)
                outcome["tool"] = name
                outcome["arguments"] = args
                if call.get("repaired"):
                    outcome["output"] = "（你输出的 JSON 格式有误，已自动修复后执行；下次请严格合法）\n{0}".format(
                        outcome.get("output", ""))
                results.append(outcome)
                yield {
                    "event": "tool_end",
                    "tool": name,
                    "arguments": args,
                    "ok": bool(outcome.get("ok", True)),
                    "output": str(outcome.get("output", ""))[:20000],
                }
                yield {"event": "changes", "changes": collector.snapshot()}
                if outcome.get("stop_task"):
                    stopped = True
                    stop_detail = str(args.get("reason") or outcome.get("reason") or "").strip()
                    break

            messages.append({"role": "user", "content": _format_results(results)})
            yield {"event": "round_done", "index": round_index, "calls": total_calls, "elapsed_ms": int((time.time() - started) * 1000)}
            if stopped:
                stop_reason = "stopped"
                yield {"event": "stopped", "reason": stop_detail,
                       "message": "模型已调用 `stop` 结束本次任务。" + (" 说明: " + stop_detail if stop_detail else "")}
                break
        else:
            stop_reason = "max_rounds"
            yield {"event": "limit", "message": "已达到最大交互轮数 {0}，请让用户继续追问。".format(max_rounds)}

    yield {
        "event": "end",
        "reason": stop_reason,
        "detail": stop_detail,
        "calls": total_calls,
        "changes": collector.snapshot(),
        "elapsed_ms": int((time.time() - started) * 1000),
    }
