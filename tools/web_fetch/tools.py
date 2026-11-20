"""抓取 URL 内容并转换成 Markdown 文本。"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

NAME = "web_fetch"
DESCRIPTION = "抓取指定 URL 的内容并转换为 Markdown：提取标题与正文，支持 HTML / 纯文本 / JSON"
PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "要抓取的完整 http(s) URL"},
        "max_chars": {"type": "integer", "description": "最多返回的字符数，默认 50000"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
    },
    "required": ["url"],
}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_DOWNLOAD = 6 * 1024 * 1024

SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header"}
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _HTMLToMarkdown(HTMLParser):
    """紧凑的 HTML -> Markdown 转换器（无第三方依赖）。"""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.skip_depth = 0
        self.in_head = 0
        self.in_pre = 0
        self.list_stack: list[str] = []
        self.link_stack: list[tuple[int, str]] = []
        self.title = ""
        self.description = ""
        self._in_title = False
        self._row: list[str] | None = None

    # ---- helpers ----
    def _emit(self, text: str) -> None:
        if text:
            self.parts.append(text)

    def _text(self) -> str:
        return "".join(self.parts)

    # ---- tags ----
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == "head":
            self.in_head += 1
            return
        if self.skip_depth:
            return
        if tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            if name in ("description", "og:description", "twitter:description") and not self.description:
                self.description = attr.get("content", "").strip()
            return
        if tag == "title":
            self._in_title = True
            return
        if self.in_head and tag not in HEADING_TAGS:
            return
        if tag in HEADING_TAGS:
            self._emit("\n\n" + "#" * HEADING_TAGS[tag] + " ")
        elif tag in ("p", "div", "section", "article", "main", "tr"):
            self._emit("\n\n")
        elif tag == "br":
            self._emit("\n")
        elif tag == "hr":
            self._emit("\n\n---\n\n")
        elif tag == "li":
            marker = "1. " if (self.list_stack and self.list_stack[-1] == "ol") else "- "
            self._emit("\n" + marker)
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
        elif tag == "pre":
            self.in_pre += 1
            self._emit("\n\n```\n")
        elif tag == "code" and not self.in_pre:
            self._emit("`")
        elif tag == "blockquote":
            self._emit("\n\n> ")
        elif tag == "a":
            self.link_stack.append((len(self.parts), attr.get("href", "")))
        elif tag == "img":
            src = urljoin(self.base_url, attr.get("src", "")) if attr.get("src") else ""
            if src and not src.startswith("data:"):
                self._emit(f"![{attr.get('alt', '')}]({src})")
        elif tag in ("td", "th"):
            self._row = self._row if self._row is not None else []
            self._emit(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "head":
            self.in_head = max(0, self.in_head - 1)
            return
        if self.skip_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag in HEADING_TAGS:
            self._emit("\n\n")
        elif tag == "pre":
            self.in_pre = max(0, self.in_pre - 1)
            self._emit("\n```\n\n")
        elif tag == "code" and not self.in_pre:
            self._emit("`")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self._emit("\n")
        elif tag == "li":
            self._emit("\n")
        elif tag == "a" and self.link_stack:
            pos, href = self.link_stack.pop()
            text = "".join(self.parts[pos:]).strip()
            del self.parts[pos:]
            if text:
                full = urljoin(self.base_url, href) if href else ""
                self._emit(f"[{text}]({full})" if full else text)
        elif tag in ("td", "th"):
            if self._row is not None:
                self._row.append("".join(self.parts).strip()[-80:])
        elif tag == "tr":
            if self._row:
                self._emit(" | ".join(c for c in self._row if c) + "\n")
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
            return
        if self.skip_depth:
            return
        if self.in_pre:
            self._emit(data)
            return
        collapsed = " ".join(data.split())
        if collapsed:
            self._emit(collapsed + " ")

    def markdown(self) -> str:
        text = self._text()
        lines = [line.rstrip() for line in text.splitlines()]
        out: list[str] = []
        blank = 0
        for line in lines:
            if not line.strip():
                blank += 1
                if blank <= 1:
                    out.append("")
            else:
                blank = 0
                out.append(line)
        return "\n".join(out).strip()


def _fetch(url: str, timeout: int) -> tuple[bytes | None, str, str, str]:
    """返回 (bytes, final_url, content_type, error)。"""

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, url, "", f"不是合法的 http(s) URL: {url}"
    try:
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(timeout, connect=15),
                          headers={"User-Agent": USER_AGENT, "Accept": "*/*"}) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    return None, str(resp.url), resp.headers.get("content-type", ""), \
                        f"HTTP {resp.status_code}: {resp.url}"
                ctype = resp.headers.get("content-type", "")
                chunks = bytearray()
                for chunk in resp.iter_bytes():
                    chunks += chunk
                    if len(chunks) > MAX_DOWNLOAD:
                        break
                return bytes(chunks), str(resp.url), ctype, ""
    except httpx.HTTPError as exc:
        return None, url, "", f"抓取失败: {exc}"


def run(url: str, max_chars: int = 50000, timeout: int = 30) -> dict:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "output": "url 不能为空"}
    timeout = max(5, min(int(timeout or 30), 120))
    max_chars = max(500, min(int(max_chars or 50000), 200000))

    data, final_url, ctype, error = _fetch(url, timeout)
    if data is None:
        return {"ok": False, "output": error}

    ctype_main = (ctype or "").split(";")[0].strip().lower()
    header = f"URL: {final_url}\nContent-Type: {ctype or '(未知)'} | {len(data)} bytes"

    if ctype_main in ("application/json",) or urlparse(final_url).path.endswith(".json"):
        try:
            pretty = json.dumps(json.loads(data.decode("utf-8", errors="replace")),
                                ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pretty = data.decode("utf-8", errors="replace")
        body = pretty[:max_chars]
        return {"output": f"{header}\n\n{body}"}

    if ctype_main and ctype_main not in ("text/html", "application/xhtml+xml", "text/plain", ""):
        return {"output": (f"{header}\n\n（非文本内容，无法转换为 Markdown；"
                           f"可尝试 execute_command + curl 下载后本地处理）")}

    text = data.decode("utf-8", errors="replace")
    if ctype_main == "text/plain":
        return {"output": f"{header}\n\n{text[:max_chars]}"}

    parser = _HTMLToMarkdown(final_url)
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"{header}\n\nHTML 解析失败: {exc}"}

    body = parser.markdown()[:max_chars]
    meta = []
    if parser.title:
        meta.append(f"Title: {parser.title}")
    if parser.description:
        meta.append(f"Description: {parser.description}")
    if not body and not meta:
        return {"ok": False, "output": f"{header}\n\n（页面未提取到文本内容，可能是 JS 渲染页面）"}
    prefix = "\n".join(meta)
    return {"output": f"{header}\n{prefix}\n\n{body}" if prefix else f"{header}\n\n{body}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
