"""正文工具调用解析器。

约定：模型通过正文调用工具，调用必须是 JSON 对象，允许一次输出多个 JSON；
非工具调用出现的花括号必须转义（写成 /{ 和 /}）。

本模块把模型正文还原成「文本片段 + 工具调用」的有序序列。
"""

from __future__ import annotations

import json

ESCAPE_CHARS = "{}[]"


def _try_parse_object(text, start):
    """从 text[start] 尝试解析一个平衡的 JSON 对象，返回 (对象, 结束下标)。"""
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
                try:
                    data = json.loads(text[start:i + 1])
                except (json.JSONDecodeError, ValueError):
                    return None, -1
                if isinstance(data, dict):
                    return data, i + 1
                return None, -1
    return None, -1
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
            obj, end = _try_parse_object(text, i)
            if obj is not None and _has_tool_name(obj):
                flush()
                call = _normalize(obj)
                call["type"] = "tool_call"
                call["raw"] = text[i:end]
                segments.append(call)
                i = end
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
