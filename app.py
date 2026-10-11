"""FastAPI 后端：认证、配置、模型、工具、技能、MCP、SSE 对话。Web 端仅做展示，所有逻辑在此实现。"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import agent_runtime
import ai_client
import config
import mcp_manager
import prompt_builder
import skill_loader
from common import read_text, relative, resolve_path
from tools import loader as tool_loader

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

app = FastAPI(title="Agents", version="1.0.0")
_sessions: dict = {}


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
async def api_login(payload: dict = Body(...)):
    cfg = config.get("auth", {}) or {}
    if not cfg.get("enabled", True):
        token = _new_token()
        _sessions[token] = {"ts": time.time()}
        return {"ok": True, "token": token, "username": "guest"}
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if username != cfg.get("username", "root") or password != cfg.get("password", "root"):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = _new_token()
    _sessions[token] = {"ts": time.time()}
    response = JSONResponse({"ok": True, "token": token, "username": username})
    response.set_cookie("agents_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return response


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    token = request.cookies.get("agents_token", "")
    _sessions.pop(token, None)
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
async def api_change_password(request: Request, payload: dict = Body(...)):
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
async def api_put_config(request: Request, payload: dict = Body(...)):
    require_auth(request)
    allowed_top = {"auth", "ai", "tool_limits", "mcp_servers", "server", "ui"}

    def _mutate(cfg):
        for key, value in (payload or {}).items():
            if key in allowed_top and isinstance(value, dict):
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
async def api_add_provider(request: Request, payload: dict = Body(...)):
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
async def api_fetch_models(pid: str, request: Request, payload: dict = Body(default={})):
    require_auth(request)
    provider = dict(_find_provider(pid))
    for key in ("base_url", "api_key", "name"):
        if payload.get(key):
            provider[key] = payload[key]
    provider["base_url"] = ai_client.normalize_base_url(provider.get("base_url", ""))
    try:
        models = await ai_client.fetch_models(provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from None

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
async def api_test_provider(pid: str, request: Request, payload: dict = Body(default={})):
    require_auth(request)
    provider = dict(_find_provider(pid))
    for key in ("base_url", "api_key"):
        if payload.get(key):
            provider[key] = payload[key]
    provider["base_url"] = ai_client.normalize_base_url(provider.get("base_url", ""))
    try:
        return await ai_client.test_provider(provider)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post("/api/providers/{pid}/select")
async def api_select_model(pid: str, request: Request, payload: dict = Body(...)):
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


@app.get("/api/tools/{name}/doc")
async def api_tool_doc(name: str, request: Request):
    require_auth(request)
    item = tool_loader.get_tool(name)
    if not item:
        raise HTTPException(status_code=404, detail="工具不存在")
    return {"name": name, "doc": item["doc"]}


@app.get("/api/skills")
async def api_skills(request: Request):
    require_auth(request)
    return {"skills": skill_loader.load_skills()}


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
async def api_chat(request: Request, payload: dict = Body(...)):
    require_auth(request)
    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    history = payload.get("history") or []
    provider_id = str(payload.get("provider_id", "") or "")
    model = str(payload.get("model", "") or "")

    async def event_stream():
        try:
            async for event in agent_runtime.run_chat(message, history, provider_id, model):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except Exception as exc:  # noqa: BLE001
            yield "data: " + json.dumps({"event": "error", "message": str(exc)}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"event": "end", "reason": "error"}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/api/health")
async def api_health():
    return {"ok": True, "tools": len(tool_loader.registry()), "workspace": str(config.workspace_dir())}


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
    config.start_watcher()
    tool_loader.refresh()
    try:
        await mcp_manager.refresh_prompt()
    except Exception as exc:  # noqa: BLE001
        print("[mcp] 初始化失败:", exc)
