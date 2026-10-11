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
import mcp_manager
import prompt_builder
import tool_parser
from common import ChangeCollector
from tools import loader as tool_loader

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
    """返回空串表示允许，否则返回拒绝原因。"""
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
    "  3) 不要有尾逗号、注释，也不要用 Markdown 代码块包裹；\n"
    "  4) content 再长也必须保持单行 JSON 字符串。"
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
        stop_reason = "completed"
        for round_index in range(1, max_rounds + 1):
            yield {"event": "round", "index": round_index}
            content = ""
            reasoning = ""
            stream_error = ""
            try:
                async for item in ai_client.stream_chat(provider, chosen_model, messages):
                    kind = item.get("type")
                    chunk = str(item.get("content") or "")
                    if kind == "thinking_delta":
                        reasoning += chunk
                        yield {"event": "thinking", "content": chunk, "delta": True}
                    elif kind == "content_delta":
                        content += chunk
                        yield {"event": "delta", "content": chunk}
            except Exception as exc:  # noqa: BLE001
                stream_error = str(exc)
                try:
                    content, reasoning = await ai_client.chat(provider, chosen_model, messages)
                except Exception as exc2:  # noqa: BLE001
                    yield {"event": "error", "message": str(exc2) or stream_error}
                    stop_reason = "error"
                    break
                yield {"event": "delta", "content": content}
                yield {"event": "fallback", "message": "流式不可用，已回退为一次性返回: " + stream_error}

            if reasoning:
                yield {"event": "thinking_done", "content": reasoning}

            segments = tool_parser.parse_segments(content)
            calls = [seg for seg in segments if seg["type"] == "tool_call"]
            broken = [seg for seg in segments if seg["type"] == "tool_call_error"]
            yield {
                "event": "message",
                "round": round_index,
                "segments": segments,
                "tool_calls": len(calls),
                "parse_errors": len(broken),
                "raw": content,
            }
            messages.append({"role": "assistant", "content": content})

            if not calls and not broken:
                stop_reason = "completed"
                break

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

            parse_streak = parse_streak + 1 if (broken and not calls) else 0
            if parse_streak >= PARSE_RETRY_LIMIT:
                yield {"event": "limit",
                       "message": "连续 {0} 轮工具调用 JSON 无法解析，已停止本轮，请检查模型输出格式。".format(parse_streak)}
                stop_reason = "parse_failed"
                break

            round_calls = 0
            for call in calls:
                name = call["tool"]
                args = call["arguments"]
                deny = _check_allowed(name, limits)
                if deny:
                    results.append({"tool": name, "arguments": args, "ok": False, "output": deny})
                    yield {"event": "tool_end", "tool": name, "arguments": args, "ok": False, "output": deny}
                    continue
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

            messages.append({"role": "user", "content": _format_results(results)})
            yield {"event": "round_done", "index": round_index, "calls": total_calls, "elapsed_ms": int((time.time() - started) * 1000)}
        else:
            stop_reason = "max_rounds"
            yield {"event": "limit", "message": "已达到最大交互轮数 {0}，请让用户继续追问。".format(max_rounds)}

    yield {
        "event": "end",
        "reason": stop_reason,
        "calls": total_calls,
        "changes": collector.snapshot(),
        "elapsed_ms": int((time.time() - started) * 1000),
    }
