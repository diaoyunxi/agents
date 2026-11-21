"""FastAPI 后端：认证、页面路由、WebSocket 通信。

所有业务操作通过 /ws 发送，后端不再暴露 REST 端点（仅保留 /api/auth/login
供登录页一次性使用，以及 /api/health 供自动更新探活）。
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import conversation_store
import mcp_manager
import ws_server
from tools import loader as tool_loader

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
CHAT_DIR = BASE_DIR / "chat"
SESSION_FILE = BASE_DIR / ".sessions.json"

app = FastAPI(title="Agents", version="2.0.0")


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #


def _load_sessions() -> dict:
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


def _logout_current(token: str) -> None:
    _sessions.pop(token, None)
    _save_sessions()


# --------------------------------------------------------------------------- #
# 唯一保留的 HTTP 端点
# --------------------------------------------------------------------------- #


@app.post("/api/auth/login")
async def api_login(payload: dict = Body(...)):
    cfg = config.get("auth", {}) or {}
    if not cfg.get("enabled", True):
        token = _new_token()
        _sessions[token] = {"ts": time.time(), "username": "guest"}
        _save_sessions()
        response = JSONResponse({"ok": True, "token": token, "username": "guest"})
        response.set_cookie("agents_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
        return response
    exp_user = str(cfg.get("username") or "")
    exp_pass = str(cfg.get("password") or "")
    if not exp_pass:
        raise HTTPException(status_code=503, detail="服务端尚未初始化登录口令，请通过 python main.py 完成初始化")
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if not (secrets.compare_digest(username, exp_user) and secrets.compare_digest(password, exp_pass)):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = _new_token()
    _sessions[token] = {"ts": time.time(), "username": username}
    _save_sessions()
    response = JSONResponse({"ok": True, "token": token, "username": username})
    response.set_cookie("agents_token", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return response


@app.get("/api/health")
async def api_health():
    return {"ok": True, "tools": len(tool_loader.registry()), "workspace": str(config.workspace_dir())}


# --------------------------------------------------------------------------- #
# WebSocket
# --------------------------------------------------------------------------- #


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await ws_server.handle_connection(
        websocket,
        auth_checker=_valid_session,
        logout_handler=lambda: None,  # 登出在 WS 内通过 op:"auth.logout" 处理
        dispatcher=ws_server.get_dispatcher(),
        task_manager=ws_server.get_task_manager(),
        registry=ws_server.get_registry(),
    )


# --------------------------------------------------------------------------- #
# 页面
# --------------------------------------------------------------------------- #

class _NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


if WEB_DIR.exists():
    app.mount("/static", _NoCacheStatic(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/chat")
async def chat_page():
    return FileResponse(str(WEB_DIR / "chat.html"))


@app.get("/settings")
async def settings_page():
    return FileResponse(str(WEB_DIR / "settings.html"))


# --------------------------------------------------------------------------- #
# 生命周期
# --------------------------------------------------------------------------- #


@app.on_event("startup")
async def on_startup():
    # 对话目录
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    # 配置监听
    config.start_watcher()
    # 工具扫描
    tool_loader.refresh()
    # MCP 初始化
    try:
        await mcp_manager.refresh_prompt()
    except Exception as exc:  # noqa: BLE001
        print("[mcp] 初始化失败:", exc)
    # WS 层初始化
    ws_server.init(
        auth_checker=_valid_session,
        logout_handler=lambda: None,
    )
