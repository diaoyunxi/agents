"""FastAPI 后端：认证、配置、模型、工具、技能、MCP、SSE 对话。Web 端仅做展示，所有逻辑在此实现。"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import agent_runtime
import ai_client
import config
import git_update
import interaction
import mcp_manager
import prompt_builder
import skill_loader
from common import read_text, relative, resolve_path
from tools import loader as tool_loader

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
CHAT_DIR = BASE_DIR / "chat"
SESSION_FILE = BASE_DIR / ".sessions.json"


def _chat_dir() -> Path:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR


def _conv_path(cid: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(cid))
    if not safe:
        raise HTTPException(status_code=400, detail="非法的对话 ID")
    return _chat_dir() / f"{safe}.json"

app = FastAPI(title="Agents", version="1.0.0")


def _load_sessions() -> dict:
    """会话落盘，确保自动更新重启后登录状态不丢失（否则用户需重新登录）。"""
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and "ts" in v}


def _save_sessions() -> None:
    try:
        SESSION_FILE.write_text(json.dumps(_sessions), encoding="utf-8")
    except OSError:
        pass


_sessions: dict = _load_sessions()


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #


def _new_token() -> str:
    return secrets.token_urlsafe(24)


def _valid_session(token: str) -> bool:
    info = _sessions.get(token)
    if not info:
        return False
    if time.time() - info["ts"] > 7 * 24 * 3600:
        _sessions.pop(token, None)
        return False
    return True


def _auth_ok(request: Request) -> bool:
    if not config.get("auth.enabled", True):
        return True
    token = request.cookies.get("agents_token", "")
    if _valid_session(token):
        return True
    header = request.headers.get("authorization", "")
    return header.startswith("Bearer ") and _valid_session(header[7:])


def require_auth(request: Request) -> None:
    if not _auth_ok(request):
        raise HTTPException(status_code=401, detail="未登录或会话已过期")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.post("/api/auth/login")
async def api_login(payload: Annotated[dict, Body()]):
    cfg = config.get("auth", {}) or {}
    if not cfg.get("enabled", True):
        token = _new_token()
        _sessions[token] = {"ts": time.time()}
        _save_sessions()
        return {"ok": True, "token": token, "username": "guest"}
    exp_user = str(cfg.get("username") or "")
    exp_pass = str(cfg.get("password") or "")
    if not exp_pass:
        # 配置中不存在可用口令。本 PR 把 DEFAULT_CONFIG 的 password 改为空串后，
        # 原先的 cfg.get("password", "root") 会取到空串而非 "root"，于是提交
        # 空密码即可登入管理员（典型触发路径：绕过 main() 用 uvicorn/gunicorn
        # 直接加载 app，使 ensure_credentials() 从未执行）。此处必须 fail closed。
        raise HTTPException(status_code=503, detail="服务端尚未初始化登录口令，请通过 python main.py 完成初始化")
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if not (secrets.compare_digest(username, exp_user) and secrets.compare_digest(password, exp_pass)):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = _new_token()
    _sessions[token] = {"ts": time.time()}
    _save_sessions()
    response = JSONResponse({"ok": True, "token": token, "username": username})
    response.set_cookie("agents_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return response


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    token = request.cookies.get("agents_token", "")
    _sessions.pop(token, None)
    _save_sessions()
    response = JSONResponse({"ok": True})
    response.delete_cookie("agents_token")
    return response


@app.get("/api/auth/status")
async def api_auth_status(request: Request):
    auth = config.get("auth", {}) or {}
    return {
        "enabled": auth.get("enabled", True),
        "setup_done": bool(auth.get("setup_done")),
        "username": auth.get("username", "root"),
        "authenticated": _auth_ok(request),
        "has_providers": bool(config.get("providers", [])),
        "active_model": config.get("ai.active_model", ""),
    }


@app.post("/api/auth/password")
async def api_change_password(request: Request, payload: Annotated[dict, Body()]):
    require_auth(request)
    old = str(payload.get("old_password", ""))
    new = str(payload.get("new_password", ""))
    if not new or len(new) < 4:
        raise HTTPException(status_code=400, detail="新密码至少 4 位")
    current = config.get("auth.password", "")
    if old != current:
        raise HTTPException(status_code=400, detail="原密码不正确")

    def _mutate(cfg):
        cfg["auth"]["password"] = new
        cfg["auth"]["setup_done"] = True

    config.update(_mutate)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #


@app.get("/api/config")
async def api_get_config(request: Request):
    require_auth(request)
    return config.public_config()


@app.put("/api/config")
async def api_put_config(request: Request, payload: Annotated[dict, Body()]):
    require_auth(request)
    allowed_top = {"auth", "ai", "tool_limits", "tool_toggles", "mcp_servers", "server", "ui", "custom"}

    server_patch = (payload or {}).get("server")
    if isinstance(server_patch, dict) and "workspace" in server_patch:
        raw = str(server_patch.get("workspace") or ".").strip() or "."
        target = config.resolve_workspace(raw)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"工作区路径不可用：{exc}")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail="工作区路径不是目录")
        server_patch["workspace"] = raw

    def _mutate(cfg):
        for key, value in (payload or {}).items():
            if key in allowed_top and isinstance(value, dict):
                # tool_toggles / custom 支持全量替换语义：前端可整体提交最新状态
                if key in ("tool_toggles", "custom"):
                    cfg[key] = value
                else:
                    cfg.setdefault(key, {}).update(value)
            elif key == "providers":
                cfg["providers"] = value
    config.update(_mutate)
    return {"ok": True, "config": config.public_config()}


@app.post("/api/config/reload")
async def api_reload_config(request: Request):
    require_auth(request)
    return {"ok": True, "config": config.load(force=True)}


# --------------------------------------------------------------------------- #
# 提供商与模型
# --------------------------------------------------------------------------- #


def _find_provider(pid: str) -> dict:
    for provider in config.get("providers", []) or []:
        if provider.get("id") == pid:
            return provider
    raise HTTPException(status_code=404, detail="提供商不存在")


@app.get("/api/providers")
async def api_list_providers(request: Request):
    require_auth(request)
    items = config.public_config().get("providers", [])
    return {"providers": items, "active": config.get("ai.active_provider_id", ""), "model": config.get("ai.active_model", "")}


@app.post("/api/providers")
async def api_add_provider(request: Request, payload: Annotated[dict, Body()]):
    require_auth(request)
    name = str(payload.get("name", "")).strip()
    base_url = str(payload.get("base_url", "")).strip()
    if not name or not base_url:
        raise HTTPException(status_code=400, detail="名称与 Base URL 必填")
    provider = {
        "id": payload.get("id") or "prov_" + secrets.token_hex(4),
        "name": name,
        "type": payload.get("type") or "openai",
        "base_url": base_url,
        "api_key": str(payload.get("api_key", "")),
        "models": [],
        "default_model": payload.get("default_model", ""),
        "headers": payload.get("headers") or {},
    }

    def _mutate(cfg):
        existing = next((p for p in cfg["providers"] if p.get("id") == provider["id"]), None)
        if existing:
            if not provider["api_key"]:
                provider["api_key"] = existing.get("api_key", "")
            existing.update(provider)
        else:
            cfg["providers"].append(provider)
        if not cfg["ai"].get("active_provider_id"):
            cfg["ai"]["active_provider_id"] = provider["id"]

    config.update(_mutate)
    return {"ok": True, "provider": provider}


@app.delete("/api/providers/{pid}")
async def api_delete_provider(pid: str, request: Request):
    require_auth(request)
    _find_provider(pid)

    def _mutate(cfg):
        cfg["providers"] = [p for p in cfg["providers"] if p.get("id") != pid]
        if cfg["ai"].get("active_provider_id") == pid:
            cfg["ai"]["active_provider_id"] = cfg["providers"][0]["id"] if cfg["providers"] else ""

    config.update(_mutate)
    return {"ok": True}


@app.post("/api/providers/{pid}/models")
async def api_fetch_models(pid: str, request: Request, payload: Annotated[dict, Body(default_factory=dict)]):
    require_auth(request)
    provider = dict(_find_provider(pid))
    for key in ("base_url", "api_key", "name"):
        if payload.get(key):
            provider[key] = payload[key]
    provider["base_url"] = ai_client.normalize_base_url(provider.get("base_url", ""))
    try:
        models = await ai_client.fetch_models(provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))

    def _mutate(cfg):
        for item in cfg["providers"]:
            if item.get("id") == pid:
                item["base_url"] = provider["base_url"]
                if payload.get("api_key"):
                    item["api_key"] = provider["api_key"]
                item["models"] = models
                item["models_updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    config.update(_mutate)
    return {"ok": True, "models": models, "count": len(models)}


@app.post("/api/providers/{pid}/test")
async def api_test_provider(pid: str, request: Request, payload: Annotated[dict, Body(default_factory=dict)]):
    require_auth(request)
    provider = dict(_find_provider(pid))
    for key in ("base_url", "api_key"):
        if payload.get(key):
            provider[key] = payload[key]
    provider["base_url"] = ai_client.normalize_base_url(provider.get("base_url", ""))
    # 若指定了 model，则按该模型类型做最小真实请求；否则回退到拉取模型列表
    model = str(payload.get("model", "") or "").strip()
    if model:
        mtype = payload.get("model_type") or ai_client.model_type_of(provider, model)
        try:
            res = await ai_client.test_model_by_type(provider, model, mtype)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": res.get("ok", False), "model": model, "model_type": res.get("type"),
                "detail": res.get("detail"), "elapsed_ms": res.get("elapsed_ms")}
    try:
        return await ai_client.test_provider(provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/providers/{pid}/invoke")
async def api_invoke_model(pid: str, request: Request, payload: dict = Body(...)):
    """按模型类型执行一次推理（非流式），请求体见 ai_client.model_inference。

    payload: {model, type?, ...按类型的字段}。type 缺省时用自动识别/覆盖。
    音频输入接受 audio_b64 / audio（base64）；语音合成/生图返回 base64 与 MIME。
    """
    require_auth(request)
    provider = dict(_find_provider(pid))
    model = str(payload.get("model", "") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model 必填")
    mtype = payload.get("type") or ai_client.model_type_of(provider, model)
    if mtype not in ai_client.MODEL_TYPES:
        raise HTTPException(status_code=400, detail="type 必须是 {0}".format("/".join(ai_client.MODEL_TYPES)))

    call_payload = {k: v for k, v in payload.items() if k not in ("model", "type")}
    try:
        out = await ai_client.model_inference(provider, model, mtype, call_payload)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))

    result = out.get("result")
    # 把二进制音频/图片转成 base64，便于 JSON 传输
    if out["type"] == "text_to_speech" and isinstance(result, dict):
        ab = result.get("audio_bytes")
        if ab is not None:
            result["audio_b64"] = base64.b64encode(ab).decode("ascii")
            result.pop("audio_bytes", None)
    return {"ok": True, "model": model, "type": out["type"], "result": result}


@app.post("/api/providers/{pid}/select")
async def api_select_model(pid: str, request: Request, payload: Annotated[dict, Body()]):
    require_auth(request)
    _find_provider(pid)
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="请选择模型")

    def _mutate(cfg):
        cfg["ai"]["active_provider_id"] = pid
        cfg["ai"]["active_model"] = model
        for item in cfg["providers"]:
            if item.get("id") == pid:
                item["default_model"] = model

    config.update(_mutate)
    return {"ok": True, "model": model}


@app.post("/api/providers/{pid}/models/type")
async def api_set_model_type(pid: str, request: Request, payload: dict = Body(...)):
    """手动覆盖某模型的类型（写入 provider.model_type_overrides）。

    payload: {"model": "模型ID", "type": "text_embedding"}；type 传空串则清除覆盖、回到自动识别。
    """
    require_auth(request)
    _find_provider(pid)
    model = str(payload.get("model", "")).strip()
    mtype = str(payload.get("type", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="model 必填")
    if mtype and mtype not in ai_client.MODEL_TYPES:
        raise HTTPException(status_code=400, detail="type 必须是 {0}".format("/".join(ai_client.MODEL_TYPES)))

    def _mutate(cfg):
        for item in cfg["providers"]:
            if item.get("id") == pid:
                overrides = item.setdefault("model_type_overrides", {})
                if mtype:
                    overrides[model] = mtype
                else:
                    overrides.pop(model, None)

    config.update(_mutate)
    return {"ok": True, "model": model, "type": mtype or ai_client.detect_model_type(model)}


@app.get("/api/models")
async def api_models(request: Request, provider_id: str = ""):
    require_auth(request)
    pid = provider_id or config.get("ai.active_provider_id", "")
    providers = config.get("providers", []) or []
    provider = next((p for p in providers if p.get("id") == pid), None)
    return {
        "provider_id": pid,
        "model": config.get("ai.active_model", ""),
        "models": (provider or {}).get("models", []),
    }


# --------------------------------------------------------------------------- #
# 工具 / 技能 / MCP
# --------------------------------------------------------------------------- #


@app.get("/api/tools")
async def api_tools(request: Request):
    require_auth(request)
    return {"tools": tool_loader.list_tools(), "limits": config.get("tool_limits", {})}


@app.post("/api/tools/refresh")
async def api_refresh_tools(request: Request):
    require_auth(request)
    tool_loader.refresh()
    return {"ok": True, "tools": tool_loader.list_tools()}


@app.post("/api/tools/toggle")
async def api_toggle_tool(request: Request, payload: dict = Body(...)):
    """允许/停用单个工具。payload: {name: str, enabled: bool}"""
    require_auth(request)
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="工具名不能为空")
    enabled = payload.get("enabled", True)

    def _mutate(cfg):
        cfg.setdefault("tool_toggles", {})[name] = bool(enabled)

    config.update(_mutate)
    return {"ok": True, "name": name, "enabled": bool(enabled)}


@app.post("/api/tools/custom-config")
async def api_custom_config(request: Request, payload: dict = Body(...)):
    """保存自定义配置（全量替换 custom 段）。payload: {key: value, ...}"""
    require_auth(request)
    custom = payload.get("custom")
    if not isinstance(custom, dict):
        raise HTTPException(status_code=400, detail="payload 必须包含 'custom' 字段（对象）")

    def _mutate(cfg):
        cfg["custom"] = custom

    config.update(_mutate)
    return {"ok": True, "custom": custom}


@app.get("/api/tools/{name}/doc")
async def api_tool_doc(name: str, request: Request):
    require_auth(request)
    item = tool_loader.get_tool(name)
    if not item:
        raise HTTPException(status_code=404, detail="工具不存在")
    return {"name": name, "doc": item["doc"]}


@app.get("/api/skills")
async def api_skills(request: Request, slim: bool = False):
    """slim=true 时只返回 name/description/when_to_use，供输入框 $ 选择器使用。"""
    require_auth(request)
    items = skill_loader.load_skills()
    if slim:
        items = [{"name": s["name"], "description": s["description"], "when_to_use": s["when_to_use"]} for s in items]
    return {"skills": items}


@app.get("/api/skill-select")
async def api_skill_select(request: Request, text: str = "", provider_id: str = "", model: str = ""):
    """预览：给定用户请求，独立选择请求将加载哪些技能（不进主对话上下文）。"""
    require_auth(request)
    import skill_selector
    result = await skill_selector.select_skills(text.strip() or "(空)", provider_id, model)
    return result


# --------------------------------------------------------------------------- #
# 用户自定义 Prompt
# --------------------------------------------------------------------------- #

_CUSTOM_PROMPT_NAME_MAX = 80
_CUSTOM_PROMPT_CONTENT_MAX = 20000
_CUSTOM_PROMPT_COUNT_MAX = 50


def _custom_prompt_values(payload: dict, current: dict | None = None) -> dict:
    """校验并规范化新增/编辑字段；已有项目在局部更新时保留未提交字段。"""
    if current is not None and not any(key in payload for key in ("name", "content", "enabled")):
        raise HTTPException(status_code=400, detail="没有可更新的 Prompt 字段")

    values = dict(current or {})
    for key in ("name", "content"):
        if key in payload:
            if not isinstance(payload[key], str):
                raise HTTPException(status_code=400, detail=f"{key} 必须是字符串")
            values[key] = payload[key].strip()
        elif current is None:
            values[key] = ""

    if "enabled" in payload:
        if type(payload["enabled"]) is not bool:
            raise HTTPException(status_code=400, detail="enabled 必须是布尔值")
        values["enabled"] = payload["enabled"]
    elif current is None or "enabled" not in values:
        # 兼容早期/手工写入、但未包含 enabled 字段的条目。
        values["enabled"] = True

    name = values.get("name", "")
    content = values.get("content", "")
    if not isinstance(name, str) or not isinstance(content, str):
        raise HTTPException(status_code=400, detail="name 和 content 必须是字符串")
    if not name:
        raise HTTPException(status_code=400, detail="Prompt 名称不能为空")
    if "\n" in name or "\r" in name:
        raise HTTPException(status_code=400, detail="Prompt 名称不能包含换行符")
    if len(name) > _CUSTOM_PROMPT_NAME_MAX:
        raise HTTPException(status_code=400, detail=f"Prompt 名称不能超过 {_CUSTOM_PROMPT_NAME_MAX} 个字符")
    if not content:
        raise HTTPException(status_code=400, detail="Prompt 内容不能为空")
    if len(content) > _CUSTOM_PROMPT_CONTENT_MAX:
        raise HTTPException(status_code=400, detail=f"Prompt 内容不能超过 {_CUSTOM_PROMPT_CONTENT_MAX} 个字符")
    return {"name": name, "content": content, "enabled": values["enabled"]}


def _editable_prompt_list(cfg: dict) -> list:
    items = cfg.get("custom_prompts")
    if not isinstance(items, list):
        items = []
        cfg["custom_prompts"] = items
    return items


def _assert_prompt_name_available(items: list, name: str, exclude_id: str = "") -> None:
    normalized = name.casefold()
    if any(isinstance(item, dict) and item.get("id") != exclude_id
           and str(item.get("name", "")).strip().casefold() == normalized for item in items):
        raise HTTPException(status_code=409, detail="已存在同名 Prompt，请使用其它名称")


@app.get("/api/prompts")
async def api_list_custom_prompts(request: Request):
    require_auth(request)
    return {"prompts": config.public_config().get("custom_prompts", [])}


@app.post("/api/prompts")
async def api_add_custom_prompt(request: Request, payload: dict = Body(...)):
    require_auth(request)
    values = _custom_prompt_values(payload)
    item = {"id": "prompt_" + secrets.token_hex(6), **values}

    def _mutate(cfg):
        items = _editable_prompt_list(cfg)
        if len(items) >= _CUSTOM_PROMPT_COUNT_MAX:
            raise HTTPException(status_code=400, detail=f"最多可保存 {_CUSTOM_PROMPT_COUNT_MAX} 个自定义 Prompt")
        _assert_prompt_name_available(items, item["name"])
        items.append(item)

    config.update(_mutate)
    return {"ok": True, "prompt": item}


@app.put("/api/prompts/{prompt_id}")
async def api_update_custom_prompt(prompt_id: str, request: Request, payload: dict = Body(...)):
    require_auth(request)
    current = next((item for item in config.get("custom_prompts", []) or []
                    if isinstance(item, dict) and item.get("id") == prompt_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    values = _custom_prompt_values(payload, current)
    item = {"id": prompt_id, **values}

    def _mutate(cfg):
        items = _editable_prompt_list(cfg)
        existing = next((entry for entry in items
                         if isinstance(entry, dict) and entry.get("id") == prompt_id), None)
        if existing is None:
            raise HTTPException(status_code=404, detail="Prompt 不存在")
        _assert_prompt_name_available(items, item["name"], exclude_id=prompt_id)
        existing.clear()
        existing.update(item)

    config.update(_mutate)
    return {"ok": True, "prompt": item}


@app.delete("/api/prompts/{prompt_id}")
async def api_delete_custom_prompt(prompt_id: str, request: Request):
    require_auth(request)

    def _mutate(cfg):
        items = _editable_prompt_list(cfg)
        index = next((idx for idx, item in enumerate(items)
                      if isinstance(item, dict) and item.get("id") == prompt_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Prompt 不存在")
        items.pop(index)

    config.update(_mutate)
    return {"ok": True, "id": prompt_id}


@app.get("/api/prompt")
async def api_prompt(request: Request):
    require_auth(request)
    await mcp_manager.refresh_prompt()
    text = prompt_builder.build_system_prompt()
    return {"prompt": text, "chars": len(text), "tools": len(tool_loader.registry())}


@app.get("/api/mcp")
async def api_mcp_list(request: Request):
    require_auth(request)
    servers = config.public_config().get("mcp_servers", [])
    return {"servers": servers, "status": await mcp_manager.status()}


@app.post("/api/mcp/refresh")
async def api_mcp_refresh(request: Request):
    require_auth(request)
    await mcp_manager.close_all()
    text = await mcp_manager.refresh_prompt()
    return {"ok": True, "prompt_chars": len(text), "status": await mcp_manager.status()}


@app.post("/api/mcp/tools")
async def api_mcp_tools(request: Request):
    require_auth(request)
    return {"tools": await mcp_manager.list_all_tools()}


# --------------------------------------------------------------------------- #
# 工作区文件
# --------------------------------------------------------------------------- #


@app.get("/api/files")
async def api_files(request: Request, path: str = ""):
    require_auth(request)
    root = config.workspace_dir()
    target = resolve_path(path or ".")
    if not target.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    items = []
    if target.is_dir():
        for entry in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            items.append({"name": entry.name, "path": relative(entry), "dir": entry.is_dir(),
                          "size": entry.stat().st_size if entry.is_file() else 0})
    return {"root": str(root), "path": relative(target) or ".", "items": items}


@app.get("/api/file")
async def api_file(request: Request, path: str):
    require_auth(request)
    target = resolve_path(path, must_exist=True)
    if target.is_dir():
        raise HTTPException(status_code=400, detail="这是目录")
    return {"path": relative(target), "content": read_text(target, limit=200000)}


# --------------------------------------------------------------------------- #
# 对话（SSE）
# --------------------------------------------------------------------------- #


@app.post("/api/chat")
async def api_chat(request: Request, payload: Annotated[dict, Body()]):
    require_auth(request)
    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    history = payload.get("history") or []
    provider_id = str(payload.get("provider_id", "") or "")
    model = str(payload.get("model", "") or "")
    workspace = str(payload.get("workspace", "") or "").strip()

    # 技能：前端用 $ 指定时为字符串列表；未指定为 None（交给 skill_selector 自动选择）
    raw_skills = payload.get("skills")
    if raw_skills is None:
        skills_param = None
    elif isinstance(raw_skills, str):
        skills_param = [raw_skills] if raw_skills.strip() else []
    elif isinstance(raw_skills, list):
        skills_param = [str(s).strip() for s in raw_skills if str(s).strip()]
    else:
        skills_param = None
    if workspace:
        ws_path = config.resolve_workspace(workspace)
        try:
            ws_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"工作区不可用：{exc}")
        if not ws_path.is_dir():
            raise HTTPException(status_code=400, detail="工作区路径不是目录，请填写目录路径")

    async def event_stream():
        try:
            with config.use_workspace(workspace):
                async for event in agent_runtime.run_chat(message, history, provider_id, model, skill_names=skills_param):
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except Exception as exc:  # noqa: BLE001
            yield "data: " + json.dumps({"event": "error", "message": str(exc)}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"event": "end", "reason": "error"}, ensure_ascii=False) + "\n\n"
        finally:
            # 客户端断开或流程结束：唤醒所有仍挂起的提问，避免工具永远等待
            interaction.cancel_all("对话流已关闭")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/api/question/{qid}/answer")
async def api_answer_question(qid: str, request: Request, payload: dict = Body(...)):
    """回答 ask_followup_question 提出的问题（多选时 answer 为字符串数组）。"""

    require_auth(request)
    item = interaction.get(qid)
    if item is None:
        raise HTTPException(status_code=404, detail="问题不存在或已过期")
    if item.get("answered"):
        raise HTTPException(status_code=409, detail="该问题已回答")
    answer = payload.get("answer")
    if item.get("multi_select"):
        if not isinstance(answer, list) or not answer:
            raise HTTPException(status_code=400, detail="该问题为多选，answer 需为非空数组")
        answer = [str(a) for a in answer]
    else:
        answer = str(answer or "").strip()
        if not answer:
            raise HTTPException(status_code=400, detail="answer 不能为空")
    if not interaction.resolve(qid, answer):
        raise HTTPException(status_code=409, detail="该问题已回答或已关闭")
    return {"ok": True, "answer": answer}


# --------------------------------------------------------------------------- #
# 对话（持久化为 chat/ 下的 JSON 文件）
# --------------------------------------------------------------------------- #


@app.get("/api/conversations")
async def api_list_conversations(request: Request):
    require_auth(request)
    items = []
    for p in sorted(_chat_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items.append({
            "id": data.get("id", p.stem),
            "title": data.get("title", "未命名对话"),
            "workspace": data.get("workspace", ""),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "message_count": len(data.get("messages", [])),
        })
    return {"conversations": items}


@app.post("/api/conversations")
async def api_create_conversation(request: Request, payload: Annotated[dict, Body(default_factory=dict)]):
    require_auth(request)
    cid = str(payload.get("id") or secrets.token_hex(8))
    title = str(payload.get("title", "新对话")).strip() or "新对话"
    workspace = str(payload.get("workspace", "") or "").strip()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    conv = {
        "id": cid,
        "title": title,
        "workspace": workspace,
        "created_at": stamp,
        "updated_at": stamp,
        "messages": [],
    }
    _conv_path(cid).write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"conversation": conv}


@app.get("/api/conversations/{cid}")
async def api_get_conversation(cid: str, request: Request):
    require_auth(request)
    path = _conv_path(cid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"conversation": json.loads(path.read_text(encoding="utf-8"))}


@app.put("/api/conversations/{cid}")
async def api_update_conversation(cid: str, request: Request, payload: Annotated[dict, Body()]):
    require_auth(request)
    path = _conv_path(cid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "title" in payload:
        data["title"] = str(payload["title"]).strip() or data.get("title", "新对话")
    if "workspace" in payload:
        data["workspace"] = str(payload.get("workspace") or "").strip()
    if "messages" in payload:
        # 支持完整消息结构：保留 tool_calls、tool_result 等字段
        new_msgs = []
        for m in (payload["messages"] or []):
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            entry = {"role": role, "content": str(m.get("content", ""))}
            # 保留原生 function calling 的工具调用信息
            if "tool_calls" in m and m["tool_calls"]:
                entry["tool_calls"] = m["tool_calls"]
            new_msgs.append(entry)
        data["messages"] = new_msgs
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"conversation": data}


@app.delete("/api/conversations/{cid}")
async def api_delete_conversation(cid: str, request: Request):
    require_auth(request)
    path = _conv_path(cid)
    if path.exists():
        path.unlink()
    return {"ok": True}


@app.get("/api/health")
async def api_health():
    return {"ok": True, "tools": len(tool_loader.registry()), "workspace": str(config.workspace_dir())}


# --------------------------------------------------------------------------- #
# 自更新（检测远端新提交 → 一键更新并重启）
# --------------------------------------------------------------------------- #


@app.get("/api/update/status")
async def api_update_status(request: Request, force: bool = False):
    """每次访问 web 都会调用：执行 git status 并比较远端分支，判断是否有新提交。"""
    require_auth(request)
    return await asyncio.to_thread(git_update.info, force)


@app.get("/api/update/result")
async def api_update_result(request: Request):
    require_auth(request)
    return git_update.read_result()


@app.post("/api/update/apply")
async def api_update_apply(request: Request):
    """一键更新：把拉取与重启交给独立的 updater.py，随后本进程自行退出。"""
    require_auth(request)
    result = await asyncio.to_thread(git_update.start_update)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "更新失败"))
    # 留出时间把响应发回浏览器，再结束自身进程，交给 updater.py 完成替换与重启
    threading.Timer(2.0, lambda: os._exit(0)).start()
    return result


# --------------------------------------------------------------------------- #
# 页面
# --------------------------------------------------------------------------- #

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/chat")
async def chat_page():
    return FileResponse(str(WEB_DIR / "chat.html"))


@app.get("/settings")
async def settings_page():
    return FileResponse(str(WEB_DIR / "settings.html"))


@app.on_event("startup")
async def on_startup():
    _chat_dir()
    config.start_watcher()
    tool_loader.refresh()
    try:
        await mcp_manager.refresh_prompt()
    except Exception as exc:  # noqa: BLE001
        print("[mcp] 初始化失败:", exc)
