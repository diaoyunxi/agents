"""新闻搜索：默认 DuckDuckGo News（无需密钥），可配置通过 Brave News API。"""

from __future__ import annotations

import httpx

import config

NAME = "news_search"
DESCRIPTION = "新闻与时效信息搜索：默认 DuckDuckGo News（免密钥），返回标题/来源/链接/摘要"
PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "新闻关键词"},
        "max_results": {"type": "integer", "description": "最多返回条数，默认 8，最大 20"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 20"},
    },
    "required": ["query"],
}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _ddg_news(query: str, max_results: int, timeout: int) -> tuple[list[dict], str]:
    """DuckDuckGo 无密钥 JSON 新闻接口。"""
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/?format=json&kl=us-en&no_html=1",
            params={"q": query, "it": "news"},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout, follow_redirects=True,
        )
        if resp.status_code >= 400:
            return [], f"HTTP {resp.status_code}"
        data = resp.json()
        results = []
        for item in (data.get("RelatedTopics") or [])[:max_results]:
            if not isinstance(item, dict) or item.get("Text") is None:
                continue  # 跳过 "More news from..." 这类无结构条目
            text = item.get("Text") or ""
            first_url = item.get("FirstURL") or ""
            title = text.split(",")[0] if "," in text else text
            results.append({"title": title[:120], "url": first_url, "snippet": text[:300]})
        if not results:
            return [], "DuckDuckGo 新闻未返回结果"
        return results, ""
    except httpx.HTTPError as exc:
        return [], str(exc)
    except (ValueError, Exception) as exc:  # noqa: BLE001
        return [], f"解析失败: {exc}"


def _brave_news(query: str, api_key: str, max_results: int, timeout: int) -> tuple[list[dict], str]:
    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/news/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return [], f"Brave News HTTP {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
            for r in (data.get("news") or [])
        ]
        return results[:max_results], ""
    except httpx.HTTPError as exc:
        return [], f"Brave News 请求失败: {exc}"
    except (ValueError, Exception) as exc:  # noqa: BLE001
        return [], f"解析失败: {exc}"


def run(query: str, max_results: int = 8, timeout: int = 20) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "output": "query 不能为空"}
    max_results = max(1, min(int(max_results or 8), 20))
    timeout = max(5, min(int(timeout or 20), 60))

    provider = str(config.get("web_search.provider", "duckduckgo") or "duckduckgo").lower()
    api_key = str(config.get("web_search.api_key", "") or "").strip()

    if provider in ("brave", "tavily"):
        results, error = _brave_news(query, api_key, max_results, timeout)
        engine = "brave-news"
    else:
        results, error = _ddg_news(query, max_results, timeout)
        engine = "duckduckgo-news"

    if not results:
        return {"ok": False, "output": f"新闻搜索失败（{engine}）: {error}"}

    lines = [f"新闻搜索: {query} | 来源: {engine} | {len(results)} 条"]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {item.get('title') or '(无标题)'}")
        lines.append(f"   {item.get('url', '')}")
        if item.get("snippet"):
            lines.append(f"   {item['snippet']}")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
