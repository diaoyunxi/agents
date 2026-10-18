"""联网搜索：默认 DuckDuckGo（无需密钥），可配置 Brave / Tavily API。"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

import config

NAME = "web_search"
DESCRIPTION = "联网搜索并返回结果列表（标题 + 链接 + 摘要）；默认 DuckDuckGo，也可配置 Brave / Tavily API"
PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "搜索关键词"},
        "max_results": {"type": "integer", "description": "最多返回条数，默认 8，最大 20"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 20"},
    },
    "required": ["query"],
}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class _DDGParser(HTMLParser):
    """解析 DuckDuckGo HTML 版结果页：a.result__a（标题+链接）与 .result__snippet（摘要）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._mode: str | None = None  # "title" | "snippet"
        self._buf: list[str] = []
        self._href = ""
        self._current: dict | None = None

    @staticmethod
    def _clean(href: str) -> str:
        if "uddg=" in href:
            try:
                qs = parse_qs(urlparse(href).query)
                if qs.get("uddg"):
                    return unquote(qs["uddg"][0])
            except (ValueError, IndexError):
                pass
        return href

    def handle_starttag(self, tag: str, attrs) -> None:
        attr = {k: (v or "") for k, v in attrs}
        cls = attr.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._mode = "title"
            self._buf = []
            self._href = self._clean(attr.get("href", ""))
        elif tag in ("a", "div") and "result__snippet" in cls:
            self._mode = "snippet"
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._mode == "title":
            text = "".join(self._buf).strip()
            if text:
                self._current = {"title": text, "url": self._href, "snippet": ""}
                self.results.append(self._current)
            self._mode = None
        elif self._mode == "snippet" and tag in ("a", "div"):
            if self._current is not None and not self._current["snippet"]:
                self._current["snippet"] = "".join(self._buf).strip()
            self._mode = None

    def handle_data(self, data: str) -> None:
        if self._mode:
            self._buf.append(data)


class _BingParser(HTMLParser):
    """解析 Bing 结果页：li.b_algo 内的 h2>a（标题+链接）与 p（摘要）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._in_algo = 0
        self._in_h2 = False
        self._mode: str | None = None  # "title" | "snippet"
        self._buf: list[str] = []
        self._href = ""
        self._current: dict | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attr = {k: (v or "") for k, v in attrs}
        cls = attr.get("class", "")
        if tag == "li" and "b_algo" in cls.split():
            self._in_algo += 1
            self._current = {"title": "", "url": "", "snippet": ""}
            self.results.append(self._current)
        elif tag == "h2" and self._in_algo:
            self._in_h2 = True
        elif (self._in_algo and self._in_h2 and tag == "a" and self._current is not None
              and not self._current["url"] and "sh_logo" not in cls):
            self._mode = "title"
            self._buf = []
            self._href = attr.get("href", "")
        elif (self._in_algo and tag == "p" and self._current is not None
              and self._current["title"] and not self._current["snippet"]):
            self._mode = "snippet"
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self._in_algo:
            self._in_algo -= 1
        elif tag == "h2" and self._in_h2:
            self._in_h2 = False
        elif self._mode == "title" and tag == "a":
            if self._current is not None:
                self._current["title"] = "".join(self._buf).strip()
                self._current["url"] = self._href
            self._mode = None
        elif self._mode == "snippet" and tag == "p":
            if self._current is not None:
                self._current["snippet"] = "".join(self._buf).strip()
            self._mode = None

    def handle_data(self, data: str) -> None:
        if self._mode:
            self._buf.append(data)


def _search_bing(query: str, max_results: int, timeout: int) -> tuple[list[dict], str]:
    try:
        resp = httpx.get(
            "https://www.bing.com/search",
            params={"q": query, "count": min(max_results, 30), "setlang": "zh-CN"},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=timeout, follow_redirects=True,
        )
        if resp.status_code >= 400:
            return [], f"HTTP {resp.status_code}"
        parser = _BingParser()
        parser.feed(resp.text)
        parser.close()
        results = [r for r in parser.results if r.get("url") and r.get("title")][:max_results]
        if results:
            return results, ""
        return [], "未解析到结果（页面结构可能变化）"
    except httpx.HTTPError as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001
        return [], f"解析失败: {exc}"


def _search_duckduckgo(query: str, max_results: int, timeout: int) -> tuple[list[dict], str, str]:
    endpoints = [
        ("https://html.duckduckgo.com/html/", {"q": query}),
        ("https://lite.duckduckgo.com/lite/", {"q": query}),
    ]
    last_error = ""
    for url, params in endpoints:
        try:
            resp = httpx.post(url, data=params, timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as exc:
            last_error = str(exc)
            continue
        if resp.status_code >= 400:
            last_error = f"HTTP {resp.status_code}"
            continue
        parser = _DDGParser()
        try:
            parser.feed(resp.text)
            parser.close()
        except Exception as exc:  # noqa: BLE001
            last_error = f"解析失败: {exc}"
            continue
        results = [r for r in parser.results if r.get("url")][:max_results]
        if results:
            return results, "", "duckduckgo"
        last_error = "未解析到结果（页面结构可能变化）"
    # DuckDuckGo 不可用（如网络环境封锁）时兜底 Bing
    results, error = _search_bing(query, max_results, timeout)
    if results:
        return results, "", "bing"
    return [], (last_error + "；Bing 兜底也失败: " + error).strip("；"), ""


def _search_brave(query: str, api_key: str, max_results: int, timeout: int) -> tuple[list[dict], str, str]:
    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return [], f"Brave API HTTP {resp.status_code}: {resp.text[:200]}", ""
        data = resp.json()
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
            for r in (data.get("web", {}).get("results") or [])
        ]
        return results[:max_results], "", "brave"
    except httpx.HTTPError as exc:
        return [], f"Brave API 请求失败: {exc}", ""
    except (json.JSONDecodeError, ValueError) as exc:
        return [], f"Brave API 响应解析失败: {exc}", ""


def _search_tavily(query: str, api_key: str, max_results: int, timeout: int) -> tuple[list[dict], str, str]:
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": min(max_results, 20)},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return [], f"Tavily API HTTP {resp.status_code}: {resp.text[:200]}", ""
        data = resp.json()
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in (data.get("results") or [])
        ]
        return results[:max_results], "", "tavily"
    except httpx.HTTPError as exc:
        return [], f"Tavily API 请求失败: {exc}", ""
    except (json.JSONDecodeError, ValueError) as exc:
        return [], f"Tavily API 响应解析失败: {exc}", ""


def run(query: str, max_results: int = 8, timeout: int = 20) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "output": "query 不能为空"}
    max_results = max(1, min(int(max_results or 8), 20))
    timeout = max(5, min(int(timeout or 20), 60))

    provider = str(config.get("web_search.provider", "duckduckgo") or "duckduckgo").strip().lower()
    api_key = str(config.get("web_search.api_key", "") or "").strip()

    if provider in ("brave", "tavily") and not api_key:
        return {"ok": False, "output": (
            f"已配置 provider={provider} 但未提供 api_key。请在设置页 config.json 的 "
            "`web_search.api_key` 填写密钥，或把 `web_search.provider` 改回 duckduckgo。")}

    if provider == "brave":
        results, error, engine = _search_brave(query, api_key, max_results, timeout)
    elif provider == "tavily":
        results, error, engine = _search_tavily(query, api_key, max_results, timeout)
    else:
        provider = "duckduckgo"
        results, error, engine = _search_duckduckgo(query, max_results, timeout)

    if error and not results:
        return {"ok": False, "output": f"搜索失败（{provider}）: {error}"}

    lines = [f"搜索: {query} | 引擎: {engine or provider} | 结果 {len(results)} 条"]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {item.get('title') or '(无标题)'}")
        lines.append(f"   {item.get('url', '')}")
        if item.get("snippet"):
            lines.append(f"   {item['snippet'][:300]}")
    if error:
        lines.append(f"（提示: {error}）")
    lines.append("\n需要阅读某条结果时，用 web_fetch 抓取对应 URL。")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
