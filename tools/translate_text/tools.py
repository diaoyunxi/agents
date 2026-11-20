"""文本翻译：默认走 MyMemory 免密钥接口，可配置自定义翻译 API。"""

from __future__ import annotations

import httpx

import config

NAME = "translate_text"
DESCRIPTION = "翻译文本（默认 MyMemory 免密钥；可在 config.json 的 custom.translate 配置自定义 API 与密钥）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "要翻译的文本"},
        "source": {"type": "string", "description": "源语言 ISO 代码，如 zh / en；省略则自动检测"},
        "target": {"type": "string", "description": "目标语言 ISO 代码，如 en / zh，必填"},
        "max_chars": {"type": "integer", "description": "最多返回的字符数，默认 4000"},
    },
    "required": ["text", "target"],
}

# MyMemory 单次请求上限 500 字符，超过则分片
_CHUNK = 450


def _split(text: str, size: int) -> list[str]:
    parts = []
    for i in range(0, len(text), size):
        parts.append(text[i:i + size])
    return parts


def _mymemory(text: str, source: str, target: str, timeout: int) -> tuple[str, str]:
    lang_from = source or "auto"
    out: list[str] = []
    errors: list[str] = []
    for chunk in _split(text, _CHUNK):
        try:
            resp = httpx.get("https://api.mymemory.translated.net/get",
                             params={"q": chunk, "source": lang_from, "target": target},
                             headers={"User-Agent": "agents-translate/1.0"}, timeout=timeout)
            data = resp.json()
            translation = (data.get("responseData") or {}).get("translatedText") or ""
            out.append(translation)
            status = (data.get("responseStatus", "") or "")
            if str(status).startswith("4") or str(status).startswith("5"):
                errors.append(f"{status} ({translation[:50]})")
        except httpx.HTTPError as exc:
            errors.append(str(exc))
    joined = " ".join(p for p in out if p.strip()).strip()
    if not joined:
        return "", ("；".join(errors) or "翻译失败")
    return joined, ""


def run(text: str, target: str, source: str = "", max_chars: int = 4000) -> dict:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "output": "text 不能为空"}
    target = (target or "").strip()
    if not target:
        return {"ok": False, "output": "target 不能为空"}
    source = (source or "").strip()
    max_chars = max(100, min(int(max_chars or 4000), 20000))

    # 若配置了自定义翻译 API，则优先使用
    custom = config.get("custom.translate", {}) or {}
    api_url = str(custom.get("api_url", "") or "").strip()
    api_key = str(custom.get("api_key", "") or "").strip()
    if api_url:
        try:
            payload = {"text": text, "source": source, "target": target}
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = httpx.post(api_url, json=payload, headers=headers, timeout=30, follow_redirects=True)
            if resp.status_code >= 400:
                return {"ok": False, "output": f"自定义翻译 API HTTP {resp.status_code}: {resp.text[:200]}"}
            data = resp.json()
            translated = data.get("translation") or data.get("text") or data.get("data") or resp.text
            return {"output": str(translated)[:max_chars]}
        except httpx.HTTPError as exc:
            return {"ok": False, "output": f"自定义翻译 API 请求失败: {exc}"}

    translated, error = _mymemory(text, source, target, 30)
    if error and not translated:
        return {"ok": False, "output": f"翻译失败（MyMemory）: {error}"}
    return {"output": f"[{source or 'auto'} -> {target}] {translated[:max_chars]}" + (f"\n（提示: {error}）" if error else "")}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
