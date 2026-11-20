"""在本机默认浏览器中预览一个 URL。"""

from __future__ import annotations

import webbrowser
from urllib.parse import urlparse

NAME = "preview_url"
DESCRIPTION = "在服务器主机的默认浏览器中打开并预览一个 http(s) URL（本地页面、本地服务、公网链接）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "要预览的完整 URL，必须以 http:// 或 https:// 开头"},
    },
    "required": ["url"],
}


def run(url: str) -> dict:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "output": "url 不能为空"}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"ok": False, "output": f"不是合法的 http(s) URL: {url}"}

    try:
        opened = webbrowser.open(url)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"打开浏览器失败: {exc}"}

    if opened:
        return {"ok": True, "output": f"已在本机默认浏览器中打开: {url}"}
    return {"ok": True, "output": (
        f"已请求打开 {url}，但主机的浏览器未确认（无图形环境时属于正常现象）。"
        "可手动在浏览器访问该地址。")}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
