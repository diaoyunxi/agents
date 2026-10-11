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
_QUOTE_CHARS = "\"“\u201d＇"
_TOOL_NAME_RE = re.compile(
    r"[\"“\u201d]?\b(?:tool|tool_name|name)\b[\"“\u201d]?\s*[:：]\s*[\"“]([A-Za-z0-9_.\-]+)"
)


def _repair_with_map(text: str, bare_quotes=frozenset()):
    """把 text 修复成合法 JSON 文本，并返回「每个输出字符对应的原文下标」。

    映射用于把 json.loads 报错的 pos 换算回原文位置，从而精准定位是哪一个
    引号漏写了转义（模型把含引号的源码塞进 content 时极常见）。

    修复项：
    - 字符串外的全角引号/冒号/逗号/括号 → 半角；
    - 字符串内的真实换行、回车、制表符 → 转义序列；
    - bare_quotes 指定的裸引号 → 补上反斜杠转义；
    - 字符串外的换行 → 空格。
    已在字符串内的内容（含中文标点）一律原样保留。
    """
    out: list[str] = []
    src: list[int] = []
    in_string = False
    escaped = False
    for idx, ch in enumerate(text):
        if in_string:
            if escaped:
                out.append(ch)
                src.append(idx)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                src.append(idx)
                escaped = True
            elif ch == "\n":
                out.extend(("\\", "n"))
                src.extend((idx, idx))
            elif ch == "\r":
                out.extend(("\\", "r"))
                src.extend((idx, idx))
            elif ch == "\t":
                out.extend(("\\", "t"))
                src.extend((idx, idx))
            elif ch == '"':
                if idx in bare_quotes:
                    # 模型漏写转义：并入字符串内容，而不是提前结束字符串
                    out.extend(("\\", '"'))
                    src.extend((idx, idx))
                else:
                    in_string = False
                    out.append('"')
                    src.append(idx)
            elif ch in "\u201d\u201e\uff02":
                in_string = False
                out.append('"')
                src.append(idx)
            else:
                out.append(ch)
                src.append(idx)
            continue
        if ch in _QUOTE_CHARS:
            in_string = True
            out.append('"')
            src.append(idx)
            continue
        if ch in "\n\r\t":
            out.append(" ")
            src.append(idx)
            continue
        out.append(FULLWIDTH_MAP.get(ch, ch))
        src.append(idx)
    return "".join(out), src


def repair_json_text(text: str, bare_quotes=frozenset()) -> str:
    """把常见的非严格 JSON 文本修复成可被 json.loads 解析的形式。

    修复项见 _repair_with_map。
    """
    return _repair_with_map(text, bare_quotes)[0]


def _scan(text, start, bare):
    """状态机扫描 text[start] 起的括号配平位置。

    bare 是「被改判为字符串内容里的裸引号」的下标集合——模型漏写 \\" 转义时，
    这些引号不应被视为字符串边界。

    返回 (end, closers)：end 为配平结束下标（不含，-1 表示未配平）；
    closers 为「在字符串内被当作结束处理」的引号下标，供回溯时挑选改判对象。
    """
    depth = 0
    in_string = False
    escaped = False
    closers: list[int] = []
    i = start
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                if i in bare:
                    i += 1
                    continue
                closers.append(i)
                in_string = False
            i += 1
            continue
        if ch == '"':
            if i in bare:
                # 已改判为内容引号：状态不变
                i += 1
                continue
            in_string = True
            i += 1
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return i + 1, closers
        i += 1
    return -1, closers


# 裸引号回溯的最大改判次数（防止病态输入下无界重扫）
BARE_QUOTE_RETRY = 64

# streaming_mask 的回溯次数上限：渲染需逐字重算，限制回溯避免卡顿
STREAM_RETRY = 4


def _is_struct_follower(text, i):
    """text[i] 处引号的下一个非空白字符是否为 JSON 结构符号（, } ] :）。"""
    j = i + 1
    while j < len(text) and text[j] in " \t\r\n":
        j += 1
    return j < len(text) and text[j] in ",}]:"


def _next_bare_candidate(text, closers, bare):
    """挑选下一个「疑似漏写转义的裸引号」下标；没有则返回 -1。

    合法 JSON 里，字符串的结束引号后面只可能是 : , } ] 之一；
    而裸引号后面多半是普通文本（如 `tip = "（运行时提醒）…`）。
    因此优先改判「后面不是结构符号」的引号，都不像时再退回按位置从后往前挑。
    """
    pool = [q for q in reversed(closers) if q not in bare]
    if not pool:
        return -1
    for q in pool:
        if not _is_struct_follower(text, q):
            return q
    return pool[0]


def _resolve_candidate(text, start, max_retry=BARE_QUOTE_RETRY):
    """确定 text[start] 起的 JSON 对象边界，并在必要时修复后解析。

    边界探测与 JSON 合法性校验放在同一个循环里：模型漏写转义（把 Python 源码里的
    "xxx" 直接塞进 content）时，字符串边界会被算错——有时表现为「未闭合」，
    有时表现为配平成功但 JSON 非法。两种情况用同一手段纠正：把某个
    「字符串结束引号」改判为内容里的裸引号，重新配平并补上转义，
    直到 json.loads 成功或用尽回溯预算。

    返回 {"obj": dict|None, "end": int, "raw": str, "error": str, "fixed": str}。
    """
    bare: set[int] = set()
    retries = 0
    # 记录首次「配平成功但 JSON 非法」的结果：若后续回溯把边界改坏，
    # 用它报错比笼统的「未闭合」更贴近真实病因。
    fallback = None
    while True:
        end, closers = _scan(text, start, frozenset(bare))
        if end < 0:
            nxt = _next_bare_candidate(text, closers, bare)
            if retries < max_retry and nxt >= 0:
                bare.add(nxt)
                retries += 1
                continue
            if fallback is not None:
                return fallback
            return {"obj": None, "end": -1, "raw": text[start:], "fixed": "",
                    "error": "JSON 对象未闭合（缺少配对的 } 或 ] ，可能被截断）"}

        raw = text[start:end]
        rel_bare = frozenset(q - start for q in bare)
        try:
            obj = json.loads(raw)
            fixed = ""
        except (json.JSONDecodeError, ValueError):
            fixed, src = _repair_with_map(raw, rel_bare)
            try:
                obj = json.loads(fixed)
            except (json.JSONDecodeError, ValueError) as exc2:
                bad = {"obj": None, "end": end, "raw": raw, "fixed": fixed,
                       "error": "JSON 解析失败（自动修复后仍不合法）：{0}".format(exc2)}
                if fallback is None:
                    fallback = bad
                # 报错位置往前回退几格即可落到「提前闭合字符串的那个引号」，
                # 把它改判为内容引号后重试——这比从后往前猜要精准得多。
                nxt = _locate_bare_quote(text, start, src, exc2, bare)
                if nxt < 0:
                    nxt = _next_bare_candidate(text, closers, bare)
                if retries < max_retry and nxt >= 0:
                    bare.add(nxt)
                    retries += 1
                    continue
                return bad
        if not isinstance(obj, dict):
            return {"obj": None, "end": end, "raw": raw, "fixed": fixed,
                    "error": "顶层不是 JSON 对象"}
        return {"obj": obj, "end": end, "raw": raw, "fixed": fixed, "error": ""}


def _locate_bare_quote(text, start, src, exc, bare):
    """由 json 解析报错位置反推「漏写转义的裸引号」在 text 中的绝对下标。

    模型漏转义时，字符串会被提前闭合，解析器紧接着在裸引号之后的第一个字符上
    报错（如 `Expecting ',' delimiter`）。因此从 pos 往前回退几格找最近的引号即可。
    找不到返回 -1。
    """
    pos = getattr(exc, "pos", None)
    if pos is None or not src:
        return -1
    for back in range(0, 4):
        if pos - back < 0:
            break
        rel = src[pos - back]
        abs_idx = start + rel
        if abs_idx in bare or abs_idx >= len(text) or text[abs_idx] != '"':
            continue
        # 跳过已被反斜杠转义的引号
        if rel > 0 and text[abs_idx - 1] == "\\":
            continue
        return abs_idx
    return -1


def _parse_candidate(text, start):
    """解析 text[start] 起的 JSON 对象（_resolve_candidate 的默认预算包装）。"""
    return _resolve_candidate(text, start)


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
    """流式渲染用：返回每个字符所属的类别序列 0=散文, 1=疑似工具JSON。

    复用 _resolve_candidate，保证「能执行」与「能高亮」对同一段文本的边界判定一致；
    回溯预算收紧到 STREAM_RETRY，避免长文本流式渲染时卡顿。
    """
    mask = [0] * len(text)
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "/" and i + 1 < len(text) and text[i + 1] in ESCAPE_CHARS:
            i += 2
            continue
        if ch == "{":
            end = _resolve_candidate(text, i, STREAM_RETRY)["end"]
            if end > 0:
                for k in range(i, end):
                    mask[k] = 1
                i = end
                continue
        i += 1
    return mask
