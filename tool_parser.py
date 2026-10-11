"""正文工具调用解析器。

约定：模型通过正文调用工具，调用必须是 JSON 对象，允许一次输出多个 JSON；
非工具调用出现的花括号必须转义（写成 /{ 和 /}）。

本模块把模型正文还原成「文本片段 + 工具调用」的有序序列。

模型并不总能输出严格合法的 JSON（最常见的是 content 里写了真实换行、
或误用中文弯引号）。因此解析分两级：
1. 直接 json.loads；
2. 失败后先做一次修复（全角符号转半角、字符串内换行转义）再 loads。
两级都失败且该片段疑似工具调用时，产出 type="tool_call_error" 的片段，
由运行时把错误回灌给模型让其重试，而不是静默降级为正文。
"""

from __future__ import annotations

import json
import re

ESCAPE_CHARS = "{}[]"

# 常见非严格写法 → 严格 JSON 的字符替换（仅作用于字符串之外）
FULLWIDTH_MAP = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\uff02": '"',
    "\uff1a": ":", "\uff0c": ",", "\uff1b": ";",
    "\uff5b": "{", "\uff5d": "}", "\uff3b": "[", "\uff3d": "]",
}
_QUOTE_CHARS = "\"“”＇"
_TOOL_NAME_RE = re.compile(
    r"[\"“”]?\b(?:tool|tool_name|name)\b[\"“”]?\s*[:：]\s*[\"“]([A-Za-z0-9_.\-]+)"
)


def repair_json_text(text: str) -> str:
    """把常见的非严格 JSON 文本修复成可被 json.loads 解析的形式。

    修复项：
    - 字符串外的全角引号/冒号/逗号/括号 → 半角；
    - 字符串内的真实换行、回车、制表符 → \\n / \\r / \\t 转义；
    - 字符串外的换行 → 空格。
    已在字符串内的内容（含中文标点）一律原样保留。
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            elif ch == '"':
                in_string = False
                out.append('"')
            elif ch in "\u201d\u201e\uff02":
                in_string = False
                out.append('"')
            else:
                out.append(ch)
            continue
        if ch in _QUOTE_CHARS:
            in_string = True
            out.append('"')
            continue
        if ch in "\n\r\t":
            out.append(" ")
            continue
        out.append(FULLWIDTH_MAP.get(ch, ch))
    return "".join(out)


def _balanced_end(text, start):
    """返回 text[start] 起的括号平衡结束下标（不含），不配平返回 -1。"""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _parse_candidate(text, start):
    """解析 text[start] 起的 JSON 对象，必要时先修复。

    返回 {"obj": dict|None, "end": int, "raw": str, "error": str, "fixed": str}。
    """
    end = _balanced_end(text, start)
    if end < 0:
        return {"obj": None, "end": -1, "raw": text[start:], "fixed": "",
                "error": "JSON 对象未闭合（缺少配对的 } 或 ] ，可能被截断）"}
    raw = text[start:end]
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        fixed = repair_json_text(raw)
        try:
            obj = json.loads(fixed)
        except (json.JSONDecodeError, ValueError) as exc2:
            return {"obj": None, "end": end, "raw": raw, "fixed": fixed,
                    "error": "JSON 解析失败（自动修复后仍不合法）：{0}".format(exc2)}
        if not isinstance(obj, dict):
            return {"obj": None, "end": end, "raw": raw, "fixed": fixed,
                    "error": "顶层不是 JSON 对象"}
        return {"obj": obj, "end": end, "raw": raw, "fixed": fixed, "error": ""}
    if not isinstance(obj, dict):
        return {"obj": None, "end": end, "raw": raw, "fixed": "",
                "error": "顶层不是 JSON 对象"}
    return {"obj": obj, "end": end, "raw": raw, "fixed": "", "error": ""}


def _looks_like_tool_call(raw):
    """宽松判断片段是否像一次工具调用（用于解析失败时决定要不要报错）。"""
    return bool(_TOOL_NAME_RE.search(raw))


def _guess_tool_name(raw):
    """从解析失败的片段里尽力猜出工具名，仅用于错误提示。"""
    m = _TOOL_NAME_RE.search(raw)
    return m.group(1) if m else ""


def _has_tool_name(obj):
    name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
    if isinstance(name, dict):
        name = name.get("name")
    return isinstance(name, str) and bool(name.strip())


def _normalize(obj):
    name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
    if isinstance(name, dict):
        name = name.get("name")
    args = obj.get("arguments")
    if args is None:
        args = obj.get("args")
    if args is None:
        args = obj.get("parameters")
    if args is None:
        args = obj.get("input")
    if args is None:
        skip = ("tool", "name", "tool_name", "id", "thought", "description")
        args = {k: v for k, v in obj.items() if k not in skip}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            args = {"input": args}
    return {
        "tool": str(name).strip(),
        "thought": obj.get("thought") or obj.get("description") or "",
        "arguments": args if isinstance(args, dict) else {"input": args},
    }


def unescape_text(text):
    """还原被转义的括号。"""
    out = []
    i = 0
    while i < len(text):
        if text[i] == "/" and i + 1 < len(text) and text[i + 1] in ESCAPE_CHARS:
            out.append(text[i + 1])
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def escape_text(text):
    out = []
    for ch in text:
        if ch in ESCAPE_CHARS:
            out.append("/")
        out.append(ch)
    return "".join(out)


def parse_segments(text):
    """把模型正文解析为有序片段列表。

    片段类型：
    - {"type": "text", "content": str}
    - {"type": "tool_call", "tool": str, "arguments": dict, "thought": str, "raw": str}
    - {"type": "tool_call_error", "tool": str, "error": str, "raw": str}
      形似工具调用但 JSON 无法解析，交由运行时回灌错误让模型重试。
    """
    segments = []
    buffer = []
    i = 0

    def flush():
        raw = "".join(buffer)
        buffer.clear()
        content = unescape_text(raw)
        if content.strip():
            segments.append({"type": "text", "content": content})

    while i < len(text):
        ch = text[i]
        if ch == "/" and i + 1 < len(text) and text[i + 1] in ESCAPE_CHARS:
            buffer.append(text[i:i + 2])
            i += 2
            continue
        if ch == "{":
            cand = _parse_candidate(text, i)
            if cand["obj"] is not None and _has_tool_name(cand["obj"]):
                flush()
                call = _normalize(cand["obj"])
                call["type"] = "tool_call"
                call["raw"] = cand["raw"]
                if cand["fixed"]:
                    call["repaired"] = True
                segments.append(call)
                i = cand["end"]
                continue
            if cand["error"] and _looks_like_tool_call(cand["raw"]):
                flush()
                segments.append({
                    "type": "tool_call_error",
                    "tool": _guess_tool_name(cand["raw"]),
                    "error": cand["error"],
                    "raw": cand["raw"],
                })
                # 未闭合时 end 为 -1，只能吞掉剩余文本交给模型重试
                i = cand["end"] if cand["end"] > 0 else len(text)
                continue
        buffer.append(ch)
        i += 1

    flush()
    return segments


def extract_tool_calls(text):
    """只返回工具调用列表（忽略文本片段）。"""
    return [seg for seg in parse_segments(text) if seg["type"] == "tool_call"]


def split_text(text):
    """只返回纯文本部分（已还原转义）。"""
    return "".join(seg["content"] for seg in parse_segments(text) if seg["type"] == "text")


def streaming_mask(text):
    """流式渲染用：返回每个字符所属的类别序列 0=散文, 1=疑似工具JSON。"""
    mask = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "/" and i + 1 < len(text) and text[i + 1] in ESCAPE_CHARS:
            mask.extend([0, 0])
            i += 2
            continue
        if ch == "{":
            depth = 0
            in_string = False
            escaped = False
            j = i
            while j < len(text):
                c = text[j]
                if in_string:
                    if escaped:
                        escaped = False
                    elif c == "\\":
                        escaped = True
                    elif c == '"':
                        in_string = False
                elif c == '"':
                    in_string = True
                elif c in "{[":
                    depth += 1
                elif c in "}]":
                    depth -= 1
                    if depth == 0:
                        break
                mask.append(1)
                j += 1
            if depth != 0:
                mask.append(0)
                i += 1
                continue
            i = j + 1
            continue
        mask.append(0)
        i += 1
    return mask
