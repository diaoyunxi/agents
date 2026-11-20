"""工具发现：按任务语义在工具名/说明/能力上做轻量检索，返回最相关的若干工具。"""

from __future__ import annotations

import re

from tools import loader

NAME = "tool_search"
DESCRIPTION = "按关键词/任务语义检索可用工具，返回最相关的工具（适合工具较多时快速定位）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "keywords": {"type": "string", "description": "空格分隔的关键词，如 `搜索 新闻 代码` 或 `file diff`"},
        "limit": {"type": "integer", "description": "最多返回条数，默认 8"},
    },
    "required": ["keywords"],
}


def _score(text: str, terms: list[str]) -> int:
    score = 0
    low = text.lower()
    for term in terms:
        if not term:
            continue
        if term.lower() in low:
            score += 2
        for chunk in re.findall(r"[a-z0-9_\-]+", term.lower()):
            if chunk and chunk in low:
                score += 1
    return score


def run(keywords: str, limit: int = 8) -> dict:
    terms = [t for t in re.split(r"[\s,，]+", (keywords or "").strip()) if t]
    if not terms:
        return {"ok": False, "output": "keywords 不能为空"}
    limit = max(1, min(int(limit or 8), 25))

    scored = []
    for t in loader.list_tools():
        hay = f"{t['name']} {t.get('description', '')}"
        s = _score(hay, terms)
        s += 1 if t.get("enabled", True) else 0  # 已启用的略优先
        if s:
            scored.append((s, t))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))

    if not scored:
        return {"output": f"没有匹配 `{keywords}` 的工具。可用: " + ", ".join(t["name"] for t in loader.list_tools())}

    lines = [f"检索 `{keywords}`：{len(scored)} 个相关工具"]
    for s, t in scored[:limit]:
        flag = "" if t.get("enabled", True) else "（停用: 缺能力）"
        lines.append(f"- {t['name']}{flag}: {t.get('description', '')}")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
