"""学术文献检索：默认 arXiv API（免密钥），可按领域配置走 PubMed。"""

from __future__ import annotations

import httpx
import xml.etree.ElementTree as ET

import config

NAME = "academic_search"
DESCRIPTION = "检索学术论文/文献：默认 arXiv（免密钥，覆盖计算机/物理/数学/量化等），可配置走 PubMed（生物医学）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "检索关键词（arXiv 支持 AND/OR/ANDNOT、作者 as:、标题 ti: 等）"},
        "max_results": {"type": "integer", "description": "最多返回条数，默认 8，最大 25"},
        "category": {"type": "string", "description": "arXiv 学科分类，如 cs.LG / cs.AI / stat.ML；省略则全学科"},
        "provider": {"type": "string", "description": "数据源：arxiv（默认）或 pubmed"},
    },
    "required": ["query"],
}

ARXIV_API = "http://export.arxiv.org/api/query"


def _arxiv(query: str, max_results: int, category: str, timeout: int) -> tuple[list[dict], str]:
    terms = [f"all:{query}"] if query else []
    if category:
        terms.append(f"cat:{category}")
    search_query = " AND ".join(terms) if terms else "all:''"
    url = f"{ARXIV_API}?search_query={search_query}&start=0&max_results={max_results}"
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        if resp.status_code >= 400:
            return [], f"HTTP {resp.status_code}"
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.content)
        results: list[dict] = []
        for entry in root.findall("atom:entry", ns):
            title = " ".join((entry.find("atom:title", ns).text or "").split())
            summary = " ".join((entry.find("atom:summary", ns).text or "").split())
            link = ""
            for a in entry.findall("atom:link", ns):
                if a.get("type") == "text/html" or not a.get("title"):
                    link = a.get("href", link)
            authors = [x.text for x in entry.findall("atom:author/atom:name", ns) if x.text]
            published = (entry.find("atom:published", ns).text or "").strip()
            results.append({
                "title": title, "url": link, "authors": authors[:6],
                "published": published, "snippet": summary[:400],
            })
        if not results:
            return [], "arXiv 未返回结果（可尝试换关键词或去掉 category）"
        return results, ""
    except httpx.HTTPError as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001
        return [], f"解析失败: {exc}"


def _pubmed(query: str, max_results: int, timeout: int) -> tuple[list[dict], str]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    api_key = str(config.get("web_search.api_key", "") or "").strip()
    params = {"db": "pubmed", "term": query, "retmax": min(max_results, 25),
              "retmode": "json", "sort": "relevance"}
    if api_key:
        params["api_key"] = api_key
    try:
        resp = httpx.get(base, params=params, timeout=timeout)
        if resp.status_code >= 400:
            return [], f"HTTP {resp.status_code}"
        ids = (resp.json().get("esearchresult", {}) or {}).get("idlist") or []
        if not ids:
            return [], "PubMed 未返回结果"
        esummary = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        resp2 = httpx.get(esummary, params={"db": "pubmed", "id": ",".join(ids),
                                             "retmode": "json", **({"api_key": api_key} if api_key else {})}, timeout=timeout)
        results = []
        for i in (resp2.json().get("result", {}) or {}):
            r = resp2.json()["result"][i]
            results.append({
                "title": " ".join((r.get("title") or "").split()),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{i}/",
                "authors": r.get("authors", [])[:6],
                "published": r.get("pubdate", ""),
                "snippet": (r.get("source") or "") + (" — " if r.get("source") else ""),
            })
        return results, ""
    except httpx.HTTPError as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001
        return [], f"解析失败: {exc}"


def run(query: str, max_results: int = 8, category: str = "", provider: str = "arxiv") -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "output": "query 不能为空"}
    max_results = max(1, min(int(max_results or 8), 25))
    provider = (provider or "arxiv").strip().lower()

    if provider == "pubmed":
        results, error = _pubmed(query, max_results, 25)
        engine = "pubmed"
    else:
        results, error = _arxiv(query, max_results, category, 25)
        engine = "arxiv"

    if not results:
        return {"ok": False, "output": f"文献检索失败（{engine}）: {error}"}

    lines = [f"学术检索: {query} | 来源: {engine}" + (f" | 分类: {category}" if category and engine == "arxiv" else "") + f" | {len(results)} 条"]
    for i, item in enumerate(results, 1):
        authors = ", ".join(item.get("authors") or [])
        lines.append(f"{i}. {item.get('title') or '(无标题)'}")
        if authors:
            lines.append(f"   作者: {authors}")
        lines.append(f"   {item.get('url', '')}")
        if item.get("published"):
            lines.append(f"   时间: {item['published']}")
        if item.get("snippet"):
            lines.append(f"   摘要: {item['snippet']}")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
