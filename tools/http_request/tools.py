"""发起任意 HTTP 请求（GET/POST/PUT/PATCH/DELETE），返回状态、头部摘要与响应体。"""

from __future__ import annotations

import json

import httpx

NAME = "http_request"
DESCRIPTION = "发起 HTTP/HTTPS 请求（任意方法、自定义头/体），返回状态码、关键响应头与响应体（截断）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "完整 http(s) URL"},
        "method": {"type": "string", "description": "方法：GET/POST/PUT/PATCH/DELETE/HEAD，默认 GET"},
        "headers": {"type": "object", "description": "可选的自定义请求头字典"},
        "body": {"type": "string", "description": "可选的请求体（原始字符串；JSON 直接给序列化好的字符串）"},
        "params": {"type": "object", "description": "可选的 query 参数字典"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 120"},
        "max_chars": {"type": "integer", "description": "响应体最多返回的字符数，默认 8000"},
    },
    "required": ["url"],
}


def run(url: str, method: str = "GET", headers: dict | None = None, body: str | None = None,
        params: dict | None = None, timeout: int = 30, max_chars: int = 8000) -> dict:
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "output": f"不是合法的 http(s) URL: {url}"}
    method = (method or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return {"ok": False, "output": f"不支持的方法: {method}"}
    timeout = max(3, min(int(timeout or 30), 120))
    max_chars = max(200, min(int(max_chars or 8000), 60000))

    req_headers = dict(headers or {})
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
            resp = client.request(method, url, headers=req_headers,
                                  content=(body.encode("utf-8") if body else None),
                                  params=params or None)
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"请求失败: {exc}"}

    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    text = resp.text if resp.text else ""
    if ctype in ("application/json",) or text.lstrip()[:1] in "{[":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, ValueError):
            pass
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [已截断，共 {len(resp.content)} 字节]"

    head_lines = [k for k in ("content-type", "content-length", "x-request-id") if k in resp.headers.lower()]
    lines = [f"{method} {url}", f"HTTP {resp.status_code} | {len(resp.content)} bytes"]
    if head_lines:
        lines.append("关键头: " + "; ".join(f"{k}={resp.headers.get(k)}" for k in head_lines))
    if text:
        lines.append("--- body ---\n" + text)
    return {"ok": resp.status_code < 400, "output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
