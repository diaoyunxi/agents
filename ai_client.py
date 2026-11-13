"""AI 提供商客户端：OpenAI 兼容接口，支持多提供商、模型列表获取与流式对话。"""

from __future__ import annotations

import base64
import asyncio
import io
import json
import re
import time
from pathlib import Path

import httpx

DEFAULT_TIMEOUT = 180

# --------------------------------------------------------------------------- #
# 模型类型（model_type）
#
# 模型列表获取后按「自动识别规则」推断每个模型的类型；请求时根据类型走不同的
# API 路径与请求体格式（chat / completions / embed / image / audio / tts /
# classify），避免把生图、语音等非对话模型按对话接口调用。
#
# 已支持的类型（MODEL_TYPES）：
#   text_generation / text_to_image / image_to_text / image_classification /
#   text_classification / translation / text_to_speech /
#   automatic_speech_recognition / voice_activity_detection / text_embedding
#
# 每个 provider 可在 provider["model_type_overrides"] = {模型ID: 类型} 中手动
# 覆盖自动识别结果。
# --------------------------------------------------------------------------- #

MODEL_TYPES = [
    "text_to_image",
    "image_to_text",
    "image_classification",
    "text_classification",
    "translation",
    "text_generation",
    "text_to_speech",
    "automatic_speech_recognition",
    "voice_activity_detection",
    "text_embedding",
]

# 类型中文名（用于界面徽章显示）
MODEL_TYPE_LABELS = {
    "text_to_image": "文生图",
    "image_to_text": "图生文",
    "image_classification": "图像分类",
    "text_classification": "文本分类",
    "translation": "翻译",
    "text_generation": "文本生成",
    "text_to_speech": "语音合成",
    "automatic_speech_recognition": "语音识别",
    "voice_activity_detection": "语音活动检测",
    "text_embedding": "文本嵌入",
}

# 按优先级排列的识别规则（正则匹配模型 ID，先命中先用）
_MODEL_TYPE_RULES = [
    ("text_to_image", re.compile(
        r"diffus|stable[-_. ]?diffus|sdxl|sd3|sd-|sdxl|dall[-_]|imagen|playground|flux|cogview|kolors|t2i|text[-_]?to[-_]?image|image[-_]?gen|coco[-_]?7b|sd-[13]\.\d|unet|midjourney|deepai",
        re.I)),
    ("image_to_text", re.compile(
        r"ocr|caption|vlm|vision|blip|llava|gpt[-_]?4o[-_]?vision|qwen[-_]?vl|pixtral|falcon[-_]?vision|sam2?[-_]?vision|image[-_]?to[-_]?text|i2t|doc(ument)?[-_]?understand",
        re.I)),
    ("image_classification", re.compile(
        r"classif|cls[-_]|resnet|vit[-_]?image|mobilenet|yolo|imagenet|detect|seg(?:ment)?|yolov?8?|ultralytics",
        re.I)),
    ("text_classification", re.compile(
        r"text[-_]?classif|sentiment|toxic|spam|ner\b|intent[-_]?class|text[-_]?cls|bert[-_]?classif",
        re.I)),
    ("translation", re.compile(
        r"translat|nllb|nmt|translate|mt[-_]?model|deepel|marian|opus[-_]?mt|glossary",
        re.I)),
    ("text_to_speech", re.compile(
        r"\btts\b|\bttss?|speech[-_]?synth|speak|voice[-_]?synth|eleven[-_]?labs?|piper[-_]?tts|edge[-_]?tts|gpt[-_]?sovi|cosyvoice|fish[-_]?speech|kittenspeech",
        re.I)),
    ("automatic_speech_recognition", re.compile(
        r"\bwhisper|\basr\b|speech[-_]?recog|transcribe|voicetype|speech[-_]?to[-_]?text|stt\b",
        re.I)),
    ("voice_activity_detection", re.compile(
        r"\bvad\b|voice[-_]?activity|silero[-_]?vad|webrtc[-_]?vad|speaker[-_]?detect",
        re.I)),
    ("text_embedding", re.compile(
        r"embed|\btext2vec|e5[-_]|gte[-_]?embed|bge|m3e|cohere[-_]?embed|openai[-_]?embed|nomic|snowflake[-_]?embed|jina[-_]?embed|conan[-_]?embed|sbert",
        re.I)),
]
_TEXT_DEFAULT_TYPES = {"text_generation", "translation"}


def detect_model_type(model_id: str, provider_type: str = "") -> str:
    """根据模型 ID 自动识别模型类型，返回 MODEL_TYPES 之一。

    识别策略（依次）：
    1. provider_type 明确为音频/图像提供商（"openai_audio"、"stability" 等）时做粗粒度兜底；
    2. 正则规则匹配模型 ID（先命中先用）；
    3. 均未命中时默认为 text_generation（按对话/生成格式请求）。
    """
    mid = str(model_id or "")
    pt = str(provider_type or "").lower()

    # 提供商级粗粒度兜底
    if pt in ("stability", "stability_ai", "midjourney"):
        if not any(rule[1].search(mid) for rule in _MODEL_TYPE_RULES if rule[0] != "text_to_image"):
            return "text_to_image"
    if pt in ("openai_audio", "whisper", "deepgram", "assemblyai", "elevenlabs", "azure_speech"):
        if not any(rule[1].search(mid) for rule in _MODEL_TYPE_RULES):
            return "text_to_speech" if pt in ("elevenlabs", "azure_speech", "openai_audio") else "automatic_speech_recognition"

    for type_name, pattern in _MODEL_TYPE_RULES:
        if pattern.search(mid):
            return type_name
    return "text_generation"


def model_type_of(provider: dict, model_id: str) -> str:
    """模型的最终类型：provider 的 model_type_overrides 优先，其次自动识别。"""
    overrides = provider.get("model_type_overrides") or {}
    override = overrides.get(model_id)
    if override in MODEL_TYPES:
        return override
    return detect_model_type(model_id, provider.get("type", ""))


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


# --------------------------------------------------------------------------- #
# HTTP 429（限流）指数退避重试
#
# 部分 LLM/提供商在并发或配额紧张时返回 429 Too Many Requests。为避免单次
# 限流就中断任务，对所有出站 LLM 请求统一做「指数退避 + 最多 7 次尝试」的
# 重试：命中 429 时按 base*2**n 递增休眠后再试，同时尊重服务端 Retry-After。
# 其它 4xx/5xx 不做重试，直接抛出（保持原有报错行为）。
# --------------------------------------------------------------------------- #

MAX_RETRIES = 7            # 总尝试次数上限（含首次）
RETRY_BASE = 1.0           # 指数退避基础秒数
RETRY_FACTOR = 2.0         # 每次翻倍
RETRY_CAP = 60.0           # 单次休眠上限（秒）


def _retry_delay(attempt: int, resp=None) -> float:
    """计算第 attempt 次（1 起）失败后的休眠秒数：指数退避，并尽量尊重 Retry-After。"""
    delay = RETRY_BASE * (RETRY_FACTOR ** (attempt - 1))
    delay = min(delay, RETRY_CAP)
    if resp is not None:
        retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        if retry_after:
            try:
                ra = float(retry_after)
                # 仅当 Retry-After 比退避值更短时才采用，避免无限等待
                delay = min(max(ra, delay), RETRY_CAP)
            except (TypeError, ValueError):
                pass
    return delay


async def _post_with_retry(client, method, url, *, label, **request_kwargs):
    """对出站 LLM 请求做 429 指数退避重试。

    透传 httpx 的请求参数（headers/json/data/files/timeout 等，见 request_kwargs）。
    命中 429 时按指数退避（1/2/4/8/16/32/60s，尊重 Retry-After）重试，最多 MAX_RETRIES
    次；其它 4xx/5xx 立即返回（调用方按原逻辑抛错）；重试耗尽仍 429 则抛带明确信息的
    ValueError。返回 httpx.Response（非流式，已可读 body/content）。
    """
    if request_kwargs.get("stream"):
        # 流式请求需 `async with client.stream(...)`，由 _stream_with_retry 处理
        raise ValueError("_post_with_retry 不支持 stream=True，请使用 _stream_with_retry")
    last_resp = None
    for attempt in range(1, MAX_RETRIES + 1):
        if method.upper() == "GET":
            last_resp = await client.get(url, **request_kwargs)
        else:
            last_resp = await client.post(url, **request_kwargs)
        if last_resp.status_code != 429:
            return last_resp
        # 命中 429：若非最后一次则退避后重试
        if attempt < MAX_RETRIES:
            await asyncio.sleep(_retry_delay(attempt, last_resp))
    body = ""
    try:
        body = (last_resp.text or "")[:500] if last_resp is not None else ""
    except Exception:  # noqa: BLE001
        body = ""
    raise ValueError(
        "{0} 请求失败：触发限流 HTTP 429，重试 {1} 次后仍被限流 {2}".format(
            label, MAX_RETRIES, body))


async def _get_with_retry(client, url, *, label, **request_kwargs):
    """GET 版本的 429 指数退避重试（用于 fetch_models）。"""
    return await _post_with_retry(client, "GET", url, label=label, **request_kwargs)


def _stream_with_retry(client, url, *, label, headers=None, json=None,
                       connect_timeout=30, **kwargs):
    """流式 POST 的 429 指数退避重试。

    命中 429 时退避重试（最多 MAX_RETRIES 次）；其它 >=400 立即抛错。
    成功时返回一个 async context manager，用法：
        async with _stream_with_retry(client, url, label=..., headers=..., json=...) as resp:
            async for line in resp.aiter_lines(): ...
    """
    import contextlib
    import contextvars

    @contextlib.asynccontextmanager
    async def _inner():
        last_body = ""
        for attempt in range(1, MAX_RETRIES + 1):
            # 用独立 stream 上下文打开，先探测状态码
            async with client.stream("POST", url, headers=headers, json=json, **kwargs) as resp:
                if resp.status_code != 429:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")
                        raise ValueError("模型请求失败 HTTP {0}: {1}".format(
                            resp.status_code, body[:500]))
                    # 成功：把已打开的流交回调用方。
                    # 注意：httpx 的 stream 上下文在此 async with 块内保持活跃，
                    # 需在此块内 yield，退出时自动关闭。
                    yield resp
                    return
                last_body = (await resp.aread()).decode("utf-8", errors="replace")[:500]
            if attempt < MAX_RETRIES:
                await asyncio.sleep(_retry_delay(attempt, None))
        raise ValueError(
            "{0} 流式请求失败：触发限流 HTTP 429，重试 {1} 次后仍被限流 {2}".format(
                label, MAX_RETRIES, last_body))

    return _inner()


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
        resp = await _get_with_retry(client, url, label="获取模型", headers=_headers(provider))
        if resp.status_code >= 400:
            raise ValueError("获取模型失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:300]))
        data = resp.json()
    items = data.get("data") if isinstance(data, dict) else data
    models = []
    ptype = provider.get("type", "")
    for item in items or []:
        if isinstance(item, str):
            mid = item
            models.append({"id": mid, "name": mid, "type": detect_model_type(mid, ptype)})
        elif isinstance(item, dict) and item.get("id"):
            mid = item["id"]
            entry = {"id": mid, "name": item.get("display_name") or mid,
                     "type": item.get("type") or detect_model_type(mid, ptype)}
            # 部分服务在 /models 里直接标注了模型类型（如 OpenAI 的 "type" 字段）
            if item.get("type") in MODEL_TYPES:
                entry["type"] = item["type"]
            models.append(entry)
    models.sort(key=lambda m: m["id"])
    return models


async def test_provider(provider):
    """连通性测试：尝试拉取模型列表。"""
    started = time.time()
    models = await fetch_models(provider)
    return {"ok": True, "count": len(models), "elapsed_ms": int((time.time() - started) * 1000)}


async def test_model_by_type(provider, model, model_type):
    """针对指定模型按其类型发一次最小真实请求，验证对应端点可用。

    各类型使用最小负载（不产生大输出），返回 {ok, type, detail}。
    """
    mtype = model_type if model_type in MODEL_TYPES else "text_generation"
    started = time.time()
    try:
        if mtype in ("text_generation", "translation", "text_classification"):
            content, _, _ = await chat(provider, model, [{"role": "user", "content": "ping"}], tools=None)
            detail = "对话端点正常，返回 {0} 字".format(len(content or ""))
        elif mtype == "text_embedding":
            data = await embed(provider, model, "hello")
            n = len(data.get("embeddings") or [])
            dim = len(data["embeddings"][0]) if n and data["embeddings"][0] else 0
            detail = "嵌入端点正常，{0} 条向量，维度 {1}".format(n, dim)
        elif mtype == "text_to_image":
            data = await image_generation(provider, model, "a red apple", size="256x256", n=1)
            detail = "生图端点正常，返回 {0} 张".format(len(data.get("images") or []))
        elif mtype in ("image_to_text", "image_classification"):
            # 1x1 透明 PNG（67 字节）作为最小可解码图片
            _TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNg"
                         "AAABCAIAAACEjQJKAAAAAElFTkSuQmCC")
            data = await model_inference(provider, model, mtype,
                                         {"image": "data:image/png;base64," + _TINY_PNG,
                                          "question": "ping"})
            detail = "多模态端点正常"
        elif mtype == "automatic_speech_recognition":
            # 440Hz 短正弦波 ~0.2s 16k 16bit mono，作为最小可解码音频
            import math
            samples = [int(12000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(3200)]
            import struct
            wav = _pcm_to_wav(struct.pack("<{}h".format(len(samples)), *samples))
            data = await audio_transcribe(provider, model, wav, filename="probe.wav")
            detail = "语音识别端点正常"
        elif mtype == "text_to_speech":
            data = await audio_speech(provider, model, "hello", voice="alloy")
            detail = "语音合成端点正常，返回 {0} 字节".format(len(data.get("audio_bytes") or b""))
        elif mtype == "voice_activity_detection":
            detail = "VAD 为自定义端点，请确认 base_url 与 provider 自定义端点"
            return {"ok": True, "type": mtype, "detail": detail,
                    "elapsed_ms": int((time.time() - started) * 1000)}
        else:
            detail = "未知类型"
        return {"ok": True, "type": mtype, "detail": detail,
                "elapsed_ms": int((time.time() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "type": mtype, "detail": str(exc),
                "elapsed_ms": int((time.time() - started) * 1000)}


def _pcm_to_wav(pcm: bytes) -> bytes:
    """PCM(16bit/16k/mono) 包装成 WAV。"""
    import struct
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm)
    return buf.getvalue()


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
        async with _stream_with_retry(client, url, label="模型流式请求",
                                       headers=_headers(provider), json=payload) as resp:
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
        resp = await _post_with_retry(client, "POST", url, label="模型请求",
                                       headers=_headers(provider), json=payload)
        if resp.status_code >= 400:
            raise ValueError("模型请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("模型未返回内容")
    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") or []
    return message.get("content") or "", message.get("reasoning_content") or "", tool_calls


# --------------------------------------------------------------------------- #
# 按模型类型走不同请求格式
#
# 不同能力类型的模型使用各自的标准 OpenAI 兼容端点与请求体：
#   - text_generation / translation / text_classification → POST /chat/completions
#   - text_embedding                                       → POST /embeddings
#   - text_to_image                                        → POST /images/generations
#   - image_to_text / image_classification                  → POST /chat/completions（多模态 image_url）
#   - automatic_speech_recognition                         → POST /audio/transcriptions
#   - text_to_speech                                       → POST /audio/speech
#   - voice_activity_detection                             → 透传 provider 自定义端点
#
# 统一入口为 model_inference()，返回一个归一化的 dict（含 type 与 result）。
# --------------------------------------------------------------------------- #


def _b64_to_bytes(data_uri: str) -> bytes:
    """把 data URI 或纯 base64 解成 bytes。"""
    raw = str(data_uri or "")
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


async def embed(provider: dict, model: str, input_text, extra: dict | None = None):
    """POST /embeddings：文本 → 向量。input_text 可为字符串或字符串列表。"""
    base = normalize_base_url(provider.get("base_url", ""))
    if not base:
        raise ValueError("请先配置 Base URL")
    payload = {"model": model, "input": input_text}
    payload.update(provider.get("extra_body") or {})
    payload.update(extra or {})
    url = base + "/embeddings"
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await _post_with_retry(client, "POST", url, label="嵌入请求",
                                       headers=_headers(provider), json=payload)
        if resp.status_code >= 400:
            raise ValueError("嵌入请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
        data = resp.json()
    if isinstance(data, dict) and "data" in data:
        vecs = [item.get("embedding") for item in data.get("data", [])]
        return {"model": model, "embeddings": vecs, "usage": data.get("usage")}
    return {"model": model, "embeddings": [data] if data else []}


async def image_generation(provider: dict, model: str, prompt: str, size: str = "", n: int = 1,
                           extra: dict | None = None):
    """POST /images/generations：文本 → 图片（base64 或 URL）。"""
    base = normalize_base_url(provider.get("base_url", ""))
    if not base:
        raise ValueError("请先配置 Base URL")
    payload = {"model": model, "prompt": prompt, "n": int(n or 1)}
    if size:
        payload["size"] = size
    payload.update(provider.get("extra_body") or {})
    payload.update(extra or {})
    url = base + "/images/generations"
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await _post_with_retry(client, "POST", url, label="生图请求",
                                       headers=_headers(provider), json=payload)
        if resp.status_code >= 400:
            raise ValueError("生图请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
        data = resp.json()
    images = []
    for item in (data.get("data") if isinstance(data, dict) else data) or []:
        if isinstance(item, dict):
            images.append({"b64": item.get("b64_json", ""), "url": item.get("url", ""),
                          "revised_prompt": item.get("revised_prompt", "")})
    return {"model": model, "images": images, "usage": data.get("usage") if isinstance(data, dict) else None}


async def audio_transcribe(provider: dict, model: str, audio_bytes: bytes,
                           filename: str = "audio.mp3", response_format: str = "json",
                           language: str = "", extra: dict | None = None):
    """POST /audio/transcriptions（multipart）：音频 → 文本。"""
    base = normalize_base_url(provider.get("base_url", ""))
    if not base:
        raise ValueError("请先配置 Base URL")
    headers = {k: v for k, v in _headers(provider).items() if k != "Content-Type"}
    data = {"model": model, "response_format": response_format}
    if language:
        data["language"] = language
    data.update(provider.get("extra_body") or {})
    data.update(extra or {})
    files = {"file": (filename, audio_bytes, "application/octet-stream")}
    url = base + "/audio/transcriptions"
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await _post_with_retry(client, "POST", url, label="语音识别请求",
                                       headers=headers, data=data, files=files)
        if resp.status_code >= 400:
            raise ValueError("语音识别请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
        if response_format == "json":
            out = resp.json()
            return {"model": model, "text": out.get("text", ""), "usage": out.get("usage")}
        return {"model": model, "text": resp.text, "usage": None}


async def audio_speech(provider: dict, model: str, text: str, voice: str = "alloy",
                       response_format: str = "mp3", extra: dict | None = None):
    """POST /audio/speech：文本 → 音频（返回音频字节与 MIME 类型）。"""
    base = normalize_base_url(provider.get("base_url", ""))
    if not base:
        raise ValueError("请先配置 Base URL")
    payload = {"model": model, "input": text, "voice": voice, "response_format": response_format}
    payload.update(provider.get("extra_body") or {})
    payload.update(extra or {})
    url = base + "/audio/speech"
    mime = "audio/" + (response_format if response_format in ("mp3", "wav", "opus", "flac", "pcm", "ogg") else "mp3")
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await _post_with_retry(client, "POST", url, label="语音合成请求",
                                       headers=_headers(provider), json=payload)
        if resp.status_code >= 400:
            raise ValueError("语音合成请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
        return {"model": model, "audio_bytes": resp.content, "mime": mime, "text_chars": len(text)}


async def model_inference(provider: dict, model: str, model_type: str, payload: dict | None = None):
    """按模型类型分发到对应端点与请求格式，返回归一化结果 dict。

    `payload` 各类型需要的字段：
      text_generation / translation / text_classification：
        {"messages": [...]}（translation 可只给 {"text","source","target"}，自动组消息）
      text_embedding：{"input": "文本或列表"}
      text_to_image：{"prompt": "...", "size": "1024x1024", "n": 1}
      image_to_text / image_classification：
        {"image": "dataURI 或 URL 或 base64", "question": "可选"}
      automatic_speech_recognition：{"audio_b64": "...", "filename": "...", "language": ""}
      text_to_speech：{"text": "...", "voice": "alloy"}
      voice_activity_detection：{"audio_b64": "..."}（透传 provider 自定义端点）
    """
    payload = dict(payload or {})
    ptype = model_type if model_type in MODEL_TYPES else "text_generation"
    extra = payload.get("extra") or {}

    if ptype in ("text_generation", "translation", "text_classification"):
        messages = payload.get("messages")
        if not messages:
            text = payload.get("text") or payload.get("prompt") or ""
            src = payload.get("source", "")
            tgt = payload.get("target", "")
            if ptype == "translation" and (src or tgt):
                sys = "You are a professional translator. Translate the user text{0}.".format(
                    " from {0} to {1}".format(src, tgt) if src or tgt else "")
                messages = [{"role": "system", "content": sys}, {"role": "user", "content": text}]
            elif ptype == "text_classification":
                msgs = [{"role": "user", "content": "Classify the following text. "
                         "Return JSON {\"label\": ..., \"confidence\": 0-1}:\n{0}".format(text)}]
                messages = msgs
            else:
                messages = [{"role": "user", "content": text}]
        content, reasoning, tool_calls = await chat(provider, model, messages, tools=None)
        result = {"text": content, "reasoning": reasoning}
        if ptype == "text_classification" and content:
            try:
                result["classification"] = json.loads(content.strip().strip("```json").strip("```"))
            except (json.JSONDecodeError, ValueError):
                result["classification"] = content
        return {"type": ptype, "result": result}

    if ptype == "text_embedding":
        inp = payload.get("input") or payload.get("text")
        if not inp:
            raise ValueError("text_embedding 需要 input 字段")
        data = await embed(provider, model, inp, extra or None)
        return {"type": ptype, "result": data}

    if ptype == "text_to_image":
        prompt = payload.get("prompt") or payload.get("text")
        if not prompt:
            raise ValueError("text_to_image 需要 prompt 字段")
        data = await image_generation(provider, model, prompt,
                                       size=payload.get("size", ""), n=int(payload.get("n", 1)),
                                       extra=extra or None)
        return {"type": ptype, "result": data}

    if ptype in ("image_to_text", "image_classification"):
        image = payload.get("image") or payload.get("image_url")
        if not image:
            raise ValueError("{0} 需要 image 字段（dataURI / base64 / URL）".format(ptype))
        if not image.startswith("data:") and not image.startswith("http"):
            image = "data:image/png;base64," + image
        question = payload.get("question") or (
            "Describe this image in detail." if ptype == "image_to_text"
            else "Classify this image. Return JSON {\"label\": ..., \"confidence\": 0-1}.")
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": image}},
            ],
        }]
        content, reasoning, _ = await chat(provider, model, messages, tools=None)
        result = {"text": content, "reasoning": reasoning}
        if ptype == "image_classification" and content:
            try:
                result["classification"] = json.loads(content.strip().strip("```json").strip("```"))
            except (json.JSONDecodeError, ValueError):
                result["classification"] = content
        return {"type": ptype, "result": result}

    if ptype == "automatic_speech_recognition":
        b64 = payload.get("audio_b64") or payload.get("audio")
        if not b64:
            raise ValueError("automatic_speech_recognition 需要 audio_b64 字段")
        audio = _b64_to_bytes(b64)
        data = await audio_transcribe(provider, model, audio,
                                       filename=payload.get("filename", "audio.mp3"),
                                       language=payload.get("language", ""),
                                       extra=extra or None)
        return {"type": ptype, "result": data}

    if ptype == "text_to_speech":
        text = payload.get("text") or payload.get("input")
        if not text:
            raise ValueError("text_to_speech 需要 text 字段")
        data = await audio_speech(provider, model, text,
                                   voice=payload.get("voice", "alloy"),
                                   extra=extra or None)
        return {"type": ptype, "result": data}

    if ptype == "voice_activity_detection":
        # 非标准类型：透传到 provider 自定义端点（payload["endpoint"]）
        endpoint = payload.get("endpoint", "")
        base = normalize_base_url(provider.get("base_url", ""))
        if not base:
            raise ValueError("请先配置 Base URL")
        target = base + (("/" + endpoint.lstrip("/")) if endpoint else "/v1/audio/vad")
        req = {k: v for k, v in payload.items() if k in ("audio_b64", "audio", "extra", "endpoint", "sample_rate")}
        req.update(extra or {})
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            resp = await _post_with_retry(client, "POST", target, label="模型推理(VAD)",
                                           headers=_headers(provider), json=req)
            if resp.status_code >= 400:
                raise ValueError("VAD 请求失败 HTTP {0}: {1}".format(resp.status_code, resp.text[:500]))
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {"raw": resp.text}
        return {"type": ptype, "result": data}

    raise ValueError("不支持的模型类型: {0}".format(model_type))
