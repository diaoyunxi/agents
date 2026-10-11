"""AI 提供商客户端：OpenAI 兼容接口，支持多提供商、模型列表获取与流式对话。"""

from __future__ import annotations

import json
import time

import httpx

DEFAULT_TIMEOUT = 180


def normalize_base_url(base_url):
    """把用户填写的 base url 规范成以 /v1 结尾的形式。"""
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return ""
    for suffix in ("/chat/completions", "/completions", "/models"):
        if url.endswith(suffix):
            url = url[:-len(suffix)]
            break
    if not url.endswith("/v1") and "/v1/" not in url:
        url = url + "/v1"
    return url


def _headers(provider):
    headers = {"Content-Type": "application/json"}
    key = (provider.get("api_key") or "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    extra = provider.get("headers") or {}
    if isinstance(extra, dict):
        headers.update({str(k): str(v) for k, v in extra.items() if v})
    return headers


def _timeout():
    import config
    try:
        return float(config.get("ai.timeout", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def build_payload(provider, model, messages, stream=True, tools=None):
    import config
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
    max_tokens = config.get("ai.max_tokens", 0)
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    temperature = config.get("ai.temperature")
    if temperature is not None:
        payload["temperature"] = float(temperature)
    payload.update(provider.get("extra_body") or {})
    return payload


async def fetch_models(provider):
    """调用 GET {base}/models 获取可用模型列表。"""
    base = normalize_base_url(provider.get("base_url", ""))
    if not base:
        raise ValueError("请先填写 Base URL")
    if not (provider.get("api_key") or "").strip():
        raise ValueError("请先填写 API Key")
    url = base + "/models"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(provider))
        if resp.status_code >= 400:
            raise ValueError("获取模型失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:300]))
        data = resp.json()
    items = data.get("data") if isinstance(data, dict) else data
    models = []
    for item in items or []:
        if isinstance(item, str):
            models.append({"id": item, "name": item})
        elif isinstance(item, dict) and item.get("id"):
            models.append({"id": item["id"], "name": item.get("display_name") or item["id"]})
    models.sort(key=lambda m: m["id"])
    return models


async def test_provider(provider):
    """连通性测试：尝试拉取模型列表。"""
    started = time.time()
    models = await fetch_models(provider)
    return {"ok": True, "count": len(models), "elapsed_ms": int((time.time() - started) * 1000)}


def _extract_delta(data):
    """从 SSE data 行中取出增量文本、思考内容与函数调用片段。"""
    choices = data.get("choices") or []
    if not choices:
        return "", "", []
    delta = choices[0].get("delta") or {}
    content = delta.get("content") or ""
    reasoning = (delta.get("reasoning_content") or delta.get("reasoning") or "")
    if isinstance(content, list):  # 兼容多模态 content 数组
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    tool_calls = delta.get("tool_calls") or []
    return content, reasoning, tool_calls


def _merge_tool_call(tool_calls, tc):
    """把流式增量里的单个 tool_calls 片段合并进 tool_calls 列表（按 index 配平）。"""
    idx = tc.get("index")
    if idx is None:
        idx = len(tool_calls)
    while len(tool_calls) <= idx:
        tool_calls.append({
            "id": None,
            "type": "function",
            "function": {"name": "", "arguments": ""},
        })
    cur = tool_calls[idx]
    if tc.get("id"):
        cur["id"] = tc["id"]
    if tc.get("type"):
        cur["type"] = tc["type"]
    fn = tc.get("function") or {}
    if fn.get("name"):
        cur["function"]["name"] += fn["name"]
    if "arguments" in fn and fn.get("arguments") is not None:
        cur["function"]["arguments"] += fn["arguments"]


async def stream_chat(provider, model, messages, tools=None):
    """流式调用对话接口，逐条产出事件字典。

    除 thinking_delta / content_delta 外，若模型发起函数调用，
    结束时额外产出一条 {"type": "tool_calls", "calls": [...]} 事件。
    """
    base = normalize_base_url(provider.get("base_url", ""))
    if not base:
        raise ValueError("请先配置 Base URL")
    url = base + "/chat/completions"
    payload = build_payload(provider, model, messages, stream=True, tools=tools)
    finish = None
    tool_calls = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(_timeout(), connect=30)) as client:
        async with client.stream("POST", url, headers=_headers(provider), json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                raise ValueError("模型请求失败 HTTP {0}: {1}".format(resp.status_code, body[:500]))
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk:
                    continue
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if data.get("error"):
                    raise ValueError("模型返回错误: {0}".format(json.dumps(data["error"], ensure_ascii=False)[:400]))
                content, reasoning, tcs = _extract_delta(data)
                for tc in tcs:
                    _merge_tool_call(tool_calls, tc)
                if reasoning:
                    yield {"type": "thinking_delta", "content": reasoning}
                if content:
                    yield {"type": "content_delta", "content": content}
                choices = data.get("choices") or []
                if choices and choices[0].get("finish_reason"):
                    finish = choices[0]["finish_reason"]
    if tool_calls:
        yield {"type": "tool_calls", "calls": tool_calls}
    yield {"type": "done", "finish_reason": finish}


async def chat(provider, model, messages, tools=None):
    """非流式调用，返回 (文本内容, 思考内容, 函数调用列表)。"""
    base = normalize_base_url(provider.get("base_url", ""))
    url = base + "/chat/completions"
    payload = build_payload(provider, model, messages, stream=False, tools=tools)
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.post(url, headers=_headers(provider), json=payload)
        if resp.status_code >= 400:
            raise ValueError("模型请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("模型未返回内容")
    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") or []
    return message.get("content") or "", message.get("reasoning_content") or "", tool_calls
