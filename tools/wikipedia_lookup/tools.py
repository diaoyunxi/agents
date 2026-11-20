"""维基百科查询：取条目摘要 + 纯文本正文若干段（REST API，免密钥）。"""

from __future__ import annotations

import httpx

NAME = "wikipedia_lookup"
DESCRIPTION = "查询维基百科条目：返回标题、摘要与正文若干段落（可指定语言版本）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "条目标题，如 变压器 / Transformer (electronics)"},
        "lang": {"type": "string", "description": "语言版本，默认 zh；可用 en/ja/de 等"},
        "paragraphs": {"type": "integer", "description": "正文最多取段落数，默认 5"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 20"},
    },
    "required": ["title"],
}


def run(title: str, lang: str = "zh", paragraphs: int = 5, timeout: int = 20) -> dict:
    title = (title or "").strip()
    if not title:
        return {"ok": False, "output": "title 不能为空"}
    lang = (lang or "zh").strip() or "zh"
    paragraphs = max(1, min(int(paragraphs or 5), 15))
    timeout = max(5, min(int(timeout or 20), 60))

    # 1) 摘要
    summary = None
    try:
        api = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
        resp = httpx.get(api, headers={"User-Agent": "agents/1.0"}, timeout=timeout)
        if resp.status_code == 404:
            return {"ok": False, "output": f"未找到 {lang} 维基条目: {title}（可试其它语言或改名）"}
        if resp.status_code < 400:
            summary = resp.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"请求失败: {exc}"}

    lines = []
    if summary:
        lines.append(f"维基条目: {summary.get('title', title)}")
        if summary.get("description"):
            lines.append(f"简介: {summary['description']}")
        if summary.get("content_urls", {}).get("desktop", {}).get("page"):
            lines.append(f"页面: {summary['content_urls']['desktop']['page']}")

    # 2) 正文纯文本
    try:
        extract_api = (f"https://{lang}.wikipedia.org/w/api.php"
                       f"?action=query&prop=extracts&explaintext=1&format=json&exintro=0"
                       f"&titles={title}")
        resp2 = httpx.get(extract_api, params={"exchars": 2000},
                          headers={"User-Agent": "agents/1.0"}, timeout=timeout)
        if resp2.status_code < 400:
            pages = resp2.json().get("query", {}).get("pages", {})
            text = next(iter(pages.values()), {}).get("extract", "") if pages else ""
            paras = [p.strip() for p in text.split("\n\n") if p.strip()]
            lines.append("正文（节选）：")
            lines.extend(paras[:paragraphs])
    except httpx.HTTPError:
        pass

    if not lines:
        return {"ok": False, "output": f"未能获取 {title} 的内容"}
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
