"""读取 RSS / Atom 订阅源，返回最新条目。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import httpx

NAME = "rss_read"
DESCRIPTION = "读取 RSS/Atom 订阅源的最新条目（标题/链接/时间/摘要）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "RSS/Atom 订阅源的 URL"},
        "max_items": {"type": "integer", "description": "最多返回条目数，默认 15"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
    },
    "required": ["url"],
}

_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _rss_items(root, limit: int) -> list[dict]:
    items = []
    for it in root.iter("item"):
        items.append({"title": _text(it.find("title")), "link": _text(it.find("link")),
                      "date": _text(it.find("pubDate")), "summary": _text(it.find("description"))[:300]})
        if len(items) >= limit:
            break
    return items


def _atom_entries(root, limit: int) -> list[dict]:
    items = []
    for it in root.iter(_ATOM + "entry"):
        link = ""
        for a in it.findall(_ATOM + "link"):
            link = a.get("href", "")
            if a.get("rel") == "alternate":
                break
        items.append({"title": _text(it.find(_ATOM + "title")), "link": link,
                      "date": _text(it.find(_ATOM + "published")) or _text(it.find(_ATOM + "updated")),
                      "summary": _text(it.find(_ATOM + "summary") or it.find(_ATOM + "content"))[:300]})
        if len(items) >= limit:
            break
    return items


def run(url: str, max_items: int = 15, timeout: int = 30) -> dict:
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "output": f"不是合法的 URL: {url}"}
    max_items = max(1, min(int(max_items or 15), 100))
    timeout = max(5, min(int(timeout or 30), 120))

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 agents-rss/1.0"})
        if resp.status_code >= 400:
            return {"ok": False, "output": f"HTTP {resp.status_code}: {url}"}
        root = ET.fromstring(resp.content)
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"请求失败: {exc}"}
    except ET.ParseError as exc:
        return {"ok": False, "output": f"XML 解析失败（可能不是 RSS/Atom）: {exc}"}

    tag = root.tag.lower()
    if "rss" in tag or "channel" in tag:
        items = _rss_items(root, max_items)
    elif "feed" in tag:
        items = _atom_entries(root, max_items)
    else:
        items = _rss_items(root, max_items) or _atom_entries(root, max_items)

    if not items:
        return {"output": f"{url} 未解析到条目（格式可能非常规）"}
    lines = [f"订阅源: {url} | {len(items)} 条"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it.get('title') or '(无标题)'}")
        if it.get("date"):
            lines.append(f"   时间: {it['date']}")
        if it.get("link"):
            lines.append(f"   {it['link']}")
        if it.get("summary"):
            lines.append(f"   {re.sub(r'<[^>]+>', '', it['summary'])}")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
