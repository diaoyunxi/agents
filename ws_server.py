"""WebSocket 服务端：连接管理、操作分发、对话任务管理、事件广播与重连回放。

所有前端请求都通过 /ws 发送，后端不再暴露 REST 端点（仅保留页面路由与一次性认证）。
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from collections import deque
from typing import Any, Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

import agent_runtime
import ai_client
import config
import conversation_store
import git_update
import interaction
import mcp_manager
import prompt_builder
import skill_loader
import skill_selector
from common import ChangeCollector, read_text, relative, resolve_path
from tools import loader as tool_loader

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

BUFFER_SIZE = 200          # 每会话事件缓冲长度（重连回放）
PING_INTERVAL = 30.0      # 心跳间隔（秒）


# --------------------------------------------------------------------------- #
# 连接注册表
# --------------------------------------------------------------------------- #


class ConnectionRegistry:
    """管理所有活跃的 WebSocket 连接，支持按会话广播与定点发送。"""

    def __init__(self) -> None:
        self._conns: dict[str, Connection] = {}  # conn_id -> Connection
        self._lock = asyncio.Lock()

    async def add(self, conn: "Connection") -> None:
        async with self._lock:
            self._conns[conn.conn_id] = conn

    async def remove(self, conn: "Connection") -> None:
        async with self._lock:
            self._conns.pop(conn.conn_id, None)

    @property
    def count(self) -> int:
        return len(self._conns)

    async def broadcast(self, event: dict, conversation_id: str = "") -> None:
        """广播事件给所有已认证连接。"""
        frame = json.dumps(event, ensure_ascii=False)
        async with self._lock:
            conns = list(self._conns.values())
        for conn in conns:
            if not conn.authenticated:
                continue
            try:
                await conn.send_raw(frame)
            except Exception:  # noqa: BLE001
                pass

    async def _send_to_conversation(self, conversation_id: str, frame: str) -> None:
        """向所有连接发送会话相关事件（广播）。"""
        async with self._lock:
            conns = list(self._conns.values())
        for conn in conns:
            if not conn.authenticated:
                continue
            try:
                await conn.send_raw(frame)
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
# 对话任务管理器
# --------------------------------------------------------------------------- #


class ChatTaskManager:
    """管理对话任务：后台运行 agent_runtime.run_chat，事件入缓冲并广播，断线不影响任务。"""

    def __init__(self, registry: ConnectionRegistry) -> None:
        self._registry = registry
        self._tasks: dict[str, asyncio.Task] = {}       # conversation_id -> Task
        self._buffers: dict[str, deque] = {}            # conversation_id -> 事件缓冲
        self._seqs: dict[str, int] = {}                  # conversation_id -> seq
        self._running: dict[str, dict] = {}              # conversation_id -> 状态
        self._lock = asyncio.Lock()

    # ---- 任务生命周期 ----

    async def start(self, conversation_id: str, message: str, history: list,
                    provider_id: str = "", model: str = "", workspace: str = "",
                    skills: list | None = None) -> str:
        """启动对话任务（后台运行），返回 session_id。"""
        async with self._lock:
            if conversation_id in self._tasks:
                raise ValueError(f"对话 {conversation_id} 已有任务在运行")
            self._buffers[conversation_id] = deque(maxlen=BUFFER_SIZE)
            self._seqs[conversation_id] = 0

        session_id = uuid.uuid4().hex[:12]
        task = asyncio.create_task(
            self._run(conversation_id, session_id, message, history,
                      provider_id, model, workspace, skills)
        )
        async with self._lock:
            self._tasks[conversation_id] = task
            self._running[conversation_id] = {
                "session_id": session_id,
                "started_at": time.time(),
                "status": "running",
            }
        return session_id

    async def stop(self, conversation_id: str) -> bool:
        """中止对话任务。"""
        async with self._lock:
            task = self._tasks.get(conversation_id)
            if task is None or task.done():
                return False
            info = self._running.get(conversation_id, {})
            info["status"] = "stopping"
        task.cancel()
        return True

    def is_running(self, conversation_id: str) -> bool:
        task = self._tasks.get(conversation_id)
        return task is not None and not task.done()

    def running_states(self) -> dict:
        """返回所有运行中/停止中任务的摘要（供重连回放）。"""
        out = {}
        for cid, info in self._running.items():
            task = self._tasks.get(cid)
            if task is not None and not task.done():
                out[cid] = info
        return out

    # ---- 事件处理 ----

    async def _emit(self, conversation_id: str, event: dict) -> None:
        """事件入缓冲并广播（附 seq，保证顺序）。"""
        buf = self._buffers.get(conversation_id)
        if buf is None:
            return
        seq = self._seqs.get(conversation_id, 0)
        self._seqs[conversation_id] = seq + 1
        event = dict(event)
        event["seq"] = seq
        buf.append(event)
        await self._registry.broadcast(event, conversation_id)

    # ---- 运行任务 ----

    async def _run(self, conversation_id: str, session_id: str, message: str,
                   history: list, provider_id: str, model: str,
                   workspace: str, skills: list | None) -> None:
        """后台运行 agent_runtime.run_chat，每个事件入缓冲并广播。"""
        try:
            conv = conversation_store.get(conversation_id) or conversation_store.create(
                cid=conversation_id, workspace=workspace)
            # 追加用户消息
            conv.setdefault("messages", []).append({"role": "user", "content": message})
            conversation_store.save(conv)

            # 发 start 事件
            start_event = {
                "event": "chat.start",
                "conversation_id": conversation_id,
                "session_id": session_id,
                "ts": int(time.time()),
            }
            await self._emit(conversation_id, start_event)

            assistant_parts: list[str] = []
            tool_calls: list[dict] = []
            tool_results: list[dict] = []

            async for event in agent_runtime.run_chat(
                message, history, provider_id, model, skill_names=skills,
            ):
                # 给事件附加元数据
                event = dict(event)
                event.setdefault("conversation_id", conversation_id)
                event.setdefault("ts", int(time.time()))
                await self._emit(conversation_id, event)

                # 收集 assistant 消息内容
                if event.get("event") == "message":
                    text = (event.get("segments") or [{}])[0].get("content", "")
                    assistant_parts.append(event.get("raw", ""))
                if event.get("event") == "tool_start":
                    tool_calls.append({
                        "id": event.get("tool_call_id"),
                        "name": event.get("tool"),
                        "arguments": event.get("arguments") or {},
                    })
                if event.get("event") == "tool_end":
                    tool_results.append({
                        "tool_call_id": event.get("tool_call_id"),
                        "tool": event.get("tool"),
                        "output": event.get("output", ""),
                        "ok": event.get("ok", False),
                    })
                if event.get("event") == "end":
                    # 保存 assistant 消息
                    content = "".join(assistant_parts)
                    msg = {"role": "assistant", "content": content}
                    if tool_calls:
                        msg["tool_calls"] = tool_calls
                    if tool_results:
                        msg["tool_results"] = tool_results
                    conv = conversation_store.get(conversation_id) or conv
                    conv.setdefault("messages", []).append(msg)
                    if not conv.get("title") or conv["title"] == "新对话":
                        conv["title"] = (message[:24] or "新对话")
                    conversation_store.save(conv)
                    assistant_parts, tool_calls, tool_results = [], [], []

        except asyncio.CancelledError:
            async with self._lock:
                info = self._running.get(conversation_id, {})
                info["status"] = "cancelled"
            cancel_event = {
                "event": "chat.stopped",
                "conversation_id": conversation_id,
                "session_id": session_id,
                "reason": "cancelled",
                "ts": int(time.time()),
            }
            await self._emit(conversation_id, cancel_event)
            raise
        except Exception as exc:  # noqa: BLE001
            error_event = {
                "event": "error",
                "conversation_id": conversation_id,
                "session_id": session_id,
                "message": str(exc),
                "ts": int(time.time()),
            }
            await self._emit(conversation_id, error_event)
            end_event = {
                "event": "end",
                "conversation_id": conversation_id,
                "session_id": session_id,
                "reason": "error",
                "ts": int(time.time()),
            }
            await self._emit(conversation_id, end_event)
        finally:
            async with self._lock:
                self._tasks.pop(conversation_id, None)
                info = self._running.get(conversation_id, {})
                if info.get("status") != "cancelled":
                    info["status"] = "finished"
                # 缓冲保留一段时间供重连回放，但不永久占用内存
                # 简单处理：任务结束后清掉缓冲
                self._buffers.pop(conversation_id, None)
                self._seqs.pop(conversation_id, None)

    def buffered_events(self, conversation_id: str) -> list[dict]:
        buf = self._buffers.get(conversation_id)
        return list(buf) if buf else []


# --------------------------------------------------------------------------- #
# 操作分发器
# --------------------------------------------------------------------------- #


class OperationDispatcher:
    """处理前端通过 WS 发来的操作帧。"""

    def __init__(self, registry: ConnectionRegistry, task_manager: ChatTaskManager) -> None:
        self._registry = registry
        self._tm = task_manager

    async def dispatch(self, conn: "Connection", op: str, data: dict,
                       msg_id: str) -> None:
        """分发操作，结果通过 ack / error 帧返回。"""
        handler = self._HANDLERS.get(op)
        if handler is None:
            await self._reply(conn, msg_id, "error", detail=f"未知操作: {op}")
            return
        try:
            result = handler(conn, data)
            # 兼容同步与异步 handler
            if asyncio.iscoroutine(result):
                result = await result
            await self._reply(conn, msg_id, "ack", data=result)
        except ValueError as exc:
            await self._reply(conn, msg_id, "error", detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            await self._reply(conn, msg_id, "error", detail=f"内部错误: {exc}")

    async def _reply(self, conn: "Connection", msg_id: str, op: str,
                     data: Any = None, detail: str = "") -> None:
        frame: dict = {"op": op, "msg_id": msg_id}
        if data is not None:
            frame["data"] = data
        if detail:
            frame["detail"] = detail
        await conn.send_json(frame)

    # ---- 各操作实现 ----

    def _auth(self, conn: "Connection", data: dict) -> dict:
        token = str(data.get("token", ""))
        # 复用 app 模块的会话校验（通过回调注入，避免循环导入）
        if conn._auth_checker and not conn._auth_checker(token):
            raise ValueError("认证失败：令牌无效或已过期")
        conn.authenticated = True
        return {"token": "ok"}

    def _auth_logout(self, conn: "Connection", data: dict) -> dict:
        if conn._logout_handler:
            conn._logout_handler()
        return {}

    def _auth_password(self, conn: "Connection", data: dict) -> dict:
        old = str(data.get("old_password", ""))
        new = str(data.get("new_password", ""))
        if not new or len(new) < 4:
            raise ValueError("新密码至少 4 位")
        current = config.get("auth.password", "")
        if old != current:
            raise ValueError("原密码不正确")

        def _mutate(cfg):
            cfg["auth"]["password"] = new
            cfg["auth"]["setup_done"] = True

        config.update(_mutate)
        return {}

    def _config_get(self, conn: "Connection", data: dict) -> dict:
        return config.public_config()

    def _config_put(self, conn: "Connection", data: dict) -> dict:
        allowed_top = {"auth", "ai", "tool_limits", "tool_toggles", "mcp_servers", "server", "ui", "custom"}
        payload = data or {}

        server_patch = payload.get("server")
        if isinstance(server_patch, dict) and "workspace" in server_patch:
            raw = str(server_patch.get("workspace") or ".").strip() or "."
            target = config.resolve_workspace(raw)
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ValueError(f"工作区路径不可用：{exc}")
            if not target.is_dir():
                raise ValueError("工作区路径不是目录")
            server_patch["workspace"] = raw

        def _mutate(cfg):
            for key, value in payload.items():
                if key in allowed_top and isinstance(value, dict):
                    if key in ("tool_toggles", "custom"):
                        cfg[key] = value
                    else:
                        cfg.setdefault(key, {}).update(value)
                elif key == "providers":
                    cfg["providers"] = value

        config.update(_mutate)
        # 广播配置变更
        asyncio.ensure_future(self._registry.broadcast({"op": "config.changed", "ts": int(time.time())}))
        return {"config": config.public_config()}

    def _config_reload(self, conn: "Connection", data: dict) -> dict:
        return {"config": config.load(force=True)}

    def _providers_list(self, conn: "Connection", data: dict) -> dict:
        items = config.public_config().get("providers", [])
        return {"providers": items, "active": config.get("ai.active_provider_id", ""),
                "model": config.get("ai.active_model", "")}

    def _providers_add(self, conn: "Connection", data: dict) -> dict:
        name = str(data.get("name", "")).strip()
        base_url = str(data.get("base_url", "")).strip()
        if not name or not base_url:
            raise ValueError("名称与 Base URL 必填")
        provider = {
            "id": data.get("id") or "prov_" + secrets.token_hex(4),
            "name": name,
            "type": data.get("type") or "openai",
            "base_url": base_url,
            "api_key": str(data.get("api_key", "")),
            "models": [],
            "default_model": data.get("default_model", ""),
            "headers": data.get("headers") or {},
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
        return {"provider": provider}

    def _providers_delete(self, conn: "Connection", data: dict) -> dict:
        pid = str(data.get("pid", ""))
        found = next((p for p in config.get("providers", []) if p.get("id") == pid), None)
        if not found:
            raise ValueError("提供商不存在")

        def _mutate(cfg):
            cfg["providers"] = [p for p in cfg["providers"] if p.get("id") != pid]
            if cfg["ai"].get("active_provider_id") == pid:
                cfg["ai"]["active_provider_id"] = cfg["providers"][0]["id"] if cfg["providers"] else ""

        config.update(_mutate)
        return {}

    async def _providers_models(self, conn: "Connection", data: dict) -> dict:
        pid = str(data.get("pid", ""))
        provider = dict(self._find_provider(pid))
        for key in ("base_url", "api_key", "name"):
            if data.get(key):
                provider[key] = data[key]
        provider["base_url"] = ai_client.normalize_base_url(provider.get("base_url", ""))
        try:
            models = await ai_client.fetch_models(provider)
        except Exception as exc:
            raise ValueError(str(exc))

        def _mutate(cfg):
            for item in cfg["providers"]:
                if item.get("id") == pid:
                    item["base_url"] = provider["base_url"]
                    if data.get("api_key"):
                        item["api_key"] = provider["api_key"]
                    item["models"] = models
                    item["models_updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        config.update(_mutate)
        return {"models": models, "count": len(models)}

    async def _providers_test(self, conn: "Connection", data: dict) -> dict:
        pid = str(data.get("pid", ""))
        provider = dict(self._find_provider(pid))
        for key in ("base_url", "api_key"):
            if data.get(key):
                provider[key] = data[key]
        provider["base_url"] = ai_client.normalize_base_url(provider.get("base_url", ""))
        model = str(data.get("model", "") or "").strip()
        if model:
            mtype = data.get("model_type") or ai_client.model_type_of(provider, model)
            try:
                res = await ai_client.test_model_by_type(provider, model, mtype)
            except Exception as exc:
                raise ValueError(str(exc))
            return {"ok": res.get("ok", False), "model": model, "model_type": res.get("type"),
                    "detail": res.get("detail"), "elapsed_ms": res.get("elapsed_ms")}
        try:
            return await ai_client.test_provider(provider)
        except Exception as exc:
            raise ValueError(str(exc))

    async def _providers_invoke(self, conn: "Connection", data: dict) -> dict:
        import base64
        pid = str(data.get("pid", ""))
        provider = dict(self._find_provider(pid))
        model = str(data.get("model", "") or "").strip()
        if not model:
            raise ValueError("model 必填")
        mtype = data.get("type") or ai_client.model_type_of(provider, model)
        if mtype not in ai_client.MODEL_TYPES:
            raise ValueError(f"type 必须是 {'/'.join(ai_client.MODEL_TYPES)}")
        call_payload = {k: v for k, v in data.items() if k not in ("pid", "model", "type")}
        try:
            out = await ai_client.model_inference(provider, model, mtype, call_payload)
        except Exception as exc:
            raise ValueError(str(exc))
        result = out.get("result")
        if out["type"] == "text_to_speech" and isinstance(result, dict):
            ab = result.get("audio_bytes")
            if ab is not None:
                result["audio_b64"] = base64.b64encode(ab).decode("ascii")
                result.pop("audio_bytes", None)
        return {"ok": True, "model": model, "type": out["type"], "result": result}

    def _providers_select(self, conn: "Connection", data: dict) -> dict:
        pid = str(data.get("pid", ""))
        self._find_provider(pid)
        model = str(data.get("model", "")).strip()
        if not model:
            raise ValueError("请选择模型")

        def _mutate(cfg):
            cfg["ai"]["active_provider_id"] = pid
            cfg["ai"]["active_model"] = model
            for item in cfg["providers"]:
                if item.get("id") == pid:
                    item["default_model"] = model

        config.update(_mutate)
        return {"model": model}

    def _providers_model_type(self, conn: "Connection", data: dict) -> dict:
        pid = str(data.get("pid", ""))
        self._find_provider(pid)
        model = str(data.get("model", "")).strip()
        mtype = str(data.get("type", "")).strip()
        if not model:
            raise ValueError("model 必填")
        if mtype and mtype not in ai_client.MODEL_TYPES:
            raise ValueError(f"type 必须是 {'/'.join(ai_client.MODEL_TYPES)}")

        def _mutate(cfg):
            for item in cfg["providers"]:
                if item.get("id") == pid:
                    overrides = item.setdefault("model_type_overrides", {})
                    if mtype:
                        overrides[model] = mtype
                    else:
                        overrides.pop(model, None)

        config.update(_mutate)
        return {"model": model, "type": mtype or ai_client.detect_model_type(model)}

    def _models_get(self, conn: "Connection", data: dict) -> dict:
        pid = data.get("provider_id") or config.get("ai.active_provider_id", "")
        providers = config.get("providers", []) or []
        provider = next((p for p in providers if p.get("id") == pid), None)
        return {
            "provider_id": pid,
            "model": config.get("ai.active_model", ""),
            "models": (provider or {}).get("models", []),
        }

    def _tools_list(self, conn: "Connection", data: dict) -> dict:
        return {"tools": tool_loader.list_tools(), "limits": config.get("tool_limits", {})}

    def _tools_refresh(self, conn: "Connection", data: dict) -> dict:
        tool_loader.refresh()
        return {"tools": tool_loader.list_tools()}

    def _tools_toggle(self, conn: "Connection", data: dict) -> dict:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("工具名不能为空")
        enabled = data.get("enabled", True)

        def _mutate(cfg):
            cfg.setdefault("tool_toggles", {})[name] = bool(enabled)

        config.update(_mutate)
        return {"name": name, "enabled": bool(enabled)}

    def _tools_custom_config(self, conn: "Connection", data: dict) -> dict:
        custom = data.get("custom")
        if not isinstance(custom, dict):
            raise ValueError("data 必须包含 'custom' 字段（对象）")

        def _mutate(cfg):
            cfg["custom"] = custom

        config.update(_mutate)
        return {"custom": custom}

    def _tools_doc(self, conn: "Connection", data: dict) -> dict:
        name = str(data.get("name", "")).strip()
        item = tool_loader.get_tool(name)
        if not item:
            raise ValueError("工具不存在")
        return {"name": name, "doc": item["doc"]}

    def _skills_list(self, conn: "Connection", data: dict) -> dict:
        items = skill_loader.load_skills()
        if data.get("slim"):
            items = [{"name": s["name"], "description": s["description"],
                      "when_to_use": s["when_to_use"]} for s in items]
        return {"skills": items}

    async def _skill_select(self, conn: "Connection", data: dict) -> dict:
        text = data.get("text", "")
        provider_id = data.get("provider_id", "")
        model = data.get("model", "")
        result = await skill_selector.select_skills(text.strip() or "(空)", provider_id, model)
        return result

    def _prompts_list(self, conn: "Connection", data: dict) -> dict:
        return {"prompts": config.public_config().get("custom_prompts", [])}

    _PROMPT_NAME_MAX = 80
    _PROMPT_CONTENT_MAX = 20000
    _PROMPT_COUNT_MAX = 50

    def _prompt_values(self, data: dict, current: dict | None = None) -> dict:
        if current is not None and not any(key in data for key in ("name", "content", "enabled")):
            raise ValueError("没有可更新的 Prompt 字段")
        values = dict(current or {})
        for key in ("name", "content"):
            if key in data:
                if not isinstance(data[key], str):
                    raise ValueError(f"{key} 必须是字符串")
                values[key] = data[key].strip()
            elif current is None:
                values[key] = ""
        if "enabled" in data:
            if type(data["enabled"]) is not bool:
                raise ValueError("enabled 必须是布尔值")
            values["enabled"] = data["enabled"]
        elif current is None or "enabled" not in values:
            values["enabled"] = True
        name = values.get("name", "")
        content = values.get("content", "")
        if not name:
            raise ValueError("Prompt 名称不能为空")
        if "\n" in name or "\r" in name:
            raise ValueError("Prompt 名称不能包含换行符")
        if len(name) > self._PROMPT_NAME_MAX:
            raise ValueError(f"Prompt 名称不能超过 {self._PROMPT_NAME_MAX} 个字符")
        if not content:
            raise ValueError("Prompt 内容不能为空")
        if len(content) > self._PROMPT_CONTENT_MAX:
            raise ValueError(f"Prompt 内容不能超过 {self._PROMPT_CONTENT_MAX} 个字符")
        return {"name": name, "content": content, "enabled": values["enabled"]}

    def _prompt_list(self, cfg: dict) -> list:
        items = cfg.get("custom_prompts")
        if not isinstance(items, list):
            items = []
            cfg["custom_prompts"] = items
        return items

    def _assert_prompt_name(self, items: list, name: str, exclude_id: str = "") -> None:
        normalized = name.casefold()
        for item in items:
            if isinstance(item, dict) and item.get("id") != exclude_id \
                    and str(item.get("name", "")).strip().casefold() == normalized:
                raise ValueError("已存在同名 Prompt，请使用其它名称")

    def _prompts_add(self, conn: "Connection", data: dict) -> dict:
        values = self._prompt_values(data)
        item = {"id": "prompt_" + secrets.token_hex(6), **values}

        def _mutate(cfg):
            items = self._prompt_list(cfg)
            if len(items) >= self._PROMPT_COUNT_MAX:
                raise ValueError(f"最多可保存 {self._PROMPT_COUNT_MAX} 个自定义 Prompt")
            self._assert_prompt_name(items, item["name"])
            items.append(item)

        config.update(_mutate)
        return {"prompt": item}

    def _prompts_update(self, conn: "Connection", data: dict) -> dict:
        prompt_id = str(data.get("id", ""))
        current = next((item for item in config.get("custom_prompts", []) or []
                        if isinstance(item, dict) and item.get("id") == prompt_id), None)
        if current is None:
            raise ValueError("Prompt 不存在")
        values = self._prompt_values(data, current)
        item = {"id": prompt_id, **values}

        def _mutate(cfg):
            items = self._prompt_list(cfg)
            existing = next((e for e in items if isinstance(e, dict) and e.get("id") == prompt_id), None)
            if existing is None:
                raise ValueError("Prompt 不存在")
            self._assert_prompt_name(items, item["name"], exclude_id=prompt_id)
            existing.clear()
            existing.update(item)

        config.update(_mutate)
        return {"prompt": item}

    def _prompts_delete(self, conn: "Connection", data: dict) -> dict:
        prompt_id = str(data.get("id", ""))

        def _mutate(cfg):
            items = self._prompt_list(cfg)
            index = next((idx for idx, item in enumerate(items)
                          if isinstance(item, dict) and item.get("id") == prompt_id), None)
            if index is None:
                raise ValueError("Prompt 不存在")
            items.pop(index)

        config.update(_mutate)
        return {"id": prompt_id}

    async def _prompt_get(self, conn: "Connection", data: dict) -> dict:
        await mcp_manager.refresh_prompt()
        text = prompt_builder.build_system_prompt()
        return {"prompt": text, "chars": len(text), "tools": len(tool_loader.registry())}

    async def _mcp_list(self, conn: "Connection", data: dict) -> dict:
        servers = config.public_config().get("mcp_servers", [])
        return {"servers": servers, "status": await mcp_manager.status()}

    async def _mcp_refresh(self, conn: "Connection", data: dict) -> dict:
        await mcp_manager.close_all()
        text = await mcp_manager.refresh_prompt()
        return {"prompt_chars": len(text), "status": await mcp_manager.status()}

    async def _mcp_tools(self, conn: "Connection", data: dict) -> dict:
        return {"tools": await mcp_manager.list_all_tools()}

    def _files_list(self, conn: "Connection", data: dict) -> dict:
        path = data.get("path", "") or "."
        root = config.workspace_dir()
        target = resolve_path(path)
        if not target.exists():
            raise ValueError("路径不存在")
        items = []
        if target.is_dir():
            for entry in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                items.append({"name": entry.name, "path": relative(entry), "dir": entry.is_dir(),
                              "size": entry.stat().st_size if entry.is_file() else 0})
        return {"root": str(root), "path": relative(target) or ".", "items": items}

    def _file_read(self, conn: "Connection", data: dict) -> dict:
        path = data.get("path", "")
        target = resolve_path(path, must_exist=True)
        if target.is_dir():
            raise ValueError("这是目录")
        return {"path": relative(target), "content": read_text(target, limit=200000)}

    # ---- 对话操作 ----

    async def _chat_send(self, conn: "Connection", data: dict) -> dict:
        message = str(data.get("message", "")).strip()
        if not message:
            raise ValueError("消息不能为空")
        conversation_id = str(data.get("conversation_id", "") or conversation_store.create()["id"])
        history = data.get("history") or []
        provider_id = str(data.get("provider_id", "") or "")
        model = str(data.get("model", "") or "")
        workspace = str(data.get("workspace", "") or "").strip()

        raw_skills = data.get("skills")
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
                raise ValueError(f"工作区不可用：{exc}")
            if not ws_path.is_dir():
                raise ValueError("工作区路径不是目录")

        # 历史消息由后端提供（从 conversation 加载），不再依赖前端传入
        conv = conversation_store.get(conversation_id)
        if conv:
            history = conv.get("messages", [])[:-1]  # 排除刚追加的 user 消息（_run 里会追加）

        session_id = await self._tm.start(
            conversation_id, message, history,
            provider_id, model, workspace, skills_param,
        )
        return {"session_id": session_id, "conversation_id": conversation_id}

    async def _chat_stop(self, conn: "Connection", data: dict) -> dict:
        conversation_id = str(data.get("conversation_id", ""))
        ok = await self._tm.stop(conversation_id)
        return {"stopped": ok}

    def _question_answer(self, conn: "Connection", data: dict) -> dict:
        qid = str(data.get("qid", ""))
        item = interaction.get(qid)
        if item is None:
            raise ValueError("问题不存在或已过期")
        if item.get("answered"):
            raise ValueError("该问题已回答")
        answer = data.get("answer")
        if item.get("multi_select"):
            if isinstance(answer, str):
                answer = [answer] if answer.strip() else []
            if not isinstance(answer, list) or not answer:
                raise ValueError("该问题为多选，answer 需为非空数组")
            answer = [str(a) for a in answer]
        else:
            if isinstance(answer, list):
                answer = answer[0] if len(answer) == 1 else None
            answer = str(answer or "").strip()
            if not answer:
                raise ValueError("answer 不能为空")
        if not interaction.resolve(qid, answer):
            raise ValueError("该问题已回答或已关闭")
        # 广播问题已回答
        asyncio.ensure_future(self._registry.broadcast({
            "op": "question.answered", "qid": qid, "answer": answer, "ts": int(time.time())
        }))
        return {"answer": answer}

    def _conversations_list(self, conn: "Connection", data: dict) -> dict:
        return {"conversations": conversation_store.list_conversations()}

    def _conversations_get(self, conn: "Connection", data: dict) -> dict:
        cid = str(data.get("cid", ""))
        conv = conversation_store.get(cid)
        if conv is None:
            raise ValueError("对话不存在")
        return {"conversation": conv}

    def _conversations_create(self, conn: "Connection", data: dict) -> dict:
        cid = str(data.get("id") or "")
        title = str(data.get("title", "新对话"))
        workspace = str(data.get("workspace", "") or "")
        conv = conversation_store.create(cid=cid, title=title, workspace=workspace)
        return {"conversation": conv}

    def _conversations_update(self, conn: "Connection", data: dict) -> dict:
        cid = str(data.get("cid", ""))
        conv = conversation_store.get(cid)
        if conv is None:
            raise ValueError("对话不存在")
        if "title" in data:
            conv["title"] = data["title"]
        if "workspace" in data:
            conv["workspace"] = data["workspace"]
        if "messages" in data:
            conv["messages"] = data["messages"]
        conv = conversation_store.save(conv)
        return {"conversation": conv}

    def _conversations_delete(self, conn: "Connection", data: dict) -> dict:
        cid = str(data.get("cid", ""))
        conversation_store.delete(cid)
        return {}

    def _health(self, conn: "Connection", data: dict) -> dict:
        return {"ok": True, "tools": len(tool_loader.registry()),
                "workspace": str(config.workspace_dir())}

    async def _update_status(self, conn: "Connection", data: dict) -> dict:
        force = bool(data.get("force", False))
        return await asyncio.to_thread(git_update.info, force)

    def _update_result(self, conn: "Connection", data: dict) -> dict:
        return git_update.read_result()

    async def _update_apply(self, conn: "Connection", data: dict) -> dict:
        import os
        import threading
        result = await asyncio.to_thread(git_update.start_update)
        if not result.get("ok"):
            raise ValueError(result.get("message", "更新失败"))
        threading.Timer(2.0, lambda: os._exit(0)).start()
        return result

    # ---- 辅助 ----

    def _find_provider(self, pid: str) -> dict:
        for provider in config.get("providers", []) or []:
            if provider.get("id") == pid:
                return provider
        raise ValueError("提供商不存在")

    # ---- op 映射表 ----

    _HANDLERS: dict[str, Callable] = {
        "auth": None,  # 特殊处理
        "auth.logout": None,
        "auth.password": None,
        "config.get": None,
        "config.put": None,
        "config.reload": None,
        "providers.list": None,
        "providers.add": None,
        "providers.delete": None,
        "providers.models": None,
        "providers.test": None,
        "providers.invoke": None,
        "providers.select": None,
        "providers.model_type": None,
        "models.get": None,
        "tools.list": None,
        "tools.refresh": None,
        "tools.toggle": None,
        "tools.custom_config": None,
        "tools.doc": None,
        "skills.list": None,
        "skill.select": None,
        "prompts.list": None,
        "prompts.add": None,
        "prompts.update": None,
        "prompts.delete": None,
        "prompt.get": None,
        "mcp.list": None,
        "mcp.refresh": None,
        "mcp.tools": None,
        "files.list": None,
        "file.read": None,
        "chat.send": None,
        "chat.stop": None,
        "question.answer": None,
        "conversations.list": None,
        "conversations.get": None,
        "conversations.create": None,
        "conversations.update": None,
        "conversations.delete": None,
        "health": None,
        "update.status": None,
        "update.result": None,
        "update.apply": None,
    }

    def _build_handlers(self) -> dict[str, Callable]:
        """构建 op -> 实际处理函数的映射。"""
        return {
            "auth": self._auth,
            "auth.logout": self._auth_logout,
            "auth.password": self._auth_password,
            "config.get": self._config_get,
            "config.put": self._config_put,
            "config.reload": self._config_reload,
            "providers.list": self._providers_list,
            "providers.add": self._providers_add,
            "providers.delete": self._providers_delete,
            "providers.models": self._providers_models,
            "providers.test": self._providers_test,
            "providers.invoke": self._providers_invoke,
            "providers.select": self._providers_select,
            "providers.model_type": self._providers_model_type,
            "models.get": self._models_get,
            "tools.list": self._tools_list,
            "tools.refresh": self._tools_refresh,
            "tools.toggle": self._tools_toggle,
            "tools.custom_config": self._tools_custom_config,
            "tools.doc": self._tools_doc,
            "skills.list": self._skills_list,
            "skill.select": self._skill_select,
            "prompts.list": self._prompts_list,
            "prompts.add": self._prompts_add,
            "prompts.update": self._prompts_update,
            "prompts.delete": self._prompts_delete,
            "prompt.get": self._prompt_get,
            "mcp.list": self._mcp_list,
            "mcp.refresh": self._mcp_refresh,
            "mcp.tools": self._mcp_tools,
            "files.list": self._files_list,
            "file.read": self._file_read,
            "chat.send": self._chat_send,
            "chat.stop": self._chat_stop,
            "question.answer": self._question_answer,
            "conversations.list": self._conversations_list,
            "conversations.get": self._conversations_get,
            "conversations.create": self._conversations_create,
            "conversations.update": self._conversations_update,
            "conversations.delete": self._conversations_delete,
            "health": self._health,
            "update.status": self._update_status,
            "update.result": self._update_result,
            "update.apply": self._update_apply,
        }


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #


@dataclass
class Connection:
    websocket: WebSocket
    conn_id: str = field(default_factory=lambda: "c_" + secrets.token_hex(6))
    authenticated: bool = False
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _auth_checker: Callable[[str], bool] | None = None
    _logout_handler: Callable[[], None] | None = None

    def __hash__(self) -> int:
        return hash(self.conn_id)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Connection) and self.conn_id == other.conn_id

    async def send_json(self, data: dict) -> None:
        async with self._send_lock:
            await self.websocket.send_text(json.dumps(data, ensure_ascii=False))

    async def send_raw(self, frame: str) -> None:
        async with self._send_lock:
            await self.websocket.send_text(frame)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# 连接处理
# --------------------------------------------------------------------------- #


async def handle_connection(websocket: WebSocket,
                            auth_checker: Callable[[str], bool] | None = None,
                            logout_handler: Callable[[], None] | None = None,
                            dispatcher: OperationDispatcher | None = None,
                            task_manager: ChatTaskManager | None = None,
                            registry: ConnectionRegistry | None = None) -> None:
    """WS 连接主循环：认证、收发操作帧、心跳、断线清理。"""
    await websocket.accept()
    conn = Connection(websocket=websocket, _auth_checker=auth_checker,
                      _logout_handler=logout_handler)
    await registry.add(conn)
    try:
        async for raw in websocket.iter_text():
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            op = frame.get("op", "")
            msg_id = frame.get("msg_id", "")

            # 心跳
            if op == "ping":
                await conn.send_json({"op": "pong", "ts": int(time.time())})
                continue

            # 认证
            if op == "auth":
                if conn.authenticated:
                    continue
                token = str(frame.get("token", ""))
                if not token:
                    # 登录 cookie 是 httponly，前端 JS 读不到；从 WS 握手的 cookie 中取
                    try:
                        token = websocket.cookies.get("agents_token", "") or ""
                    except Exception:
                        token = ""
                if auth_checker and not auth_checker(token):
                    await conn.send_json({"op": "auth_result", "ok": False,
                                          "detail": "认证失败"})
                    continue
                conn.authenticated = True
                await conn.send_json({"op": "auth_result", "ok": True})
                continue

            if op == "resync":
                # 重连回放：发送缓冲事件 + 挂起问题 + 运行中任务状态
                replay: dict = {}
                last_event_id = str(frame.get("last_event_id", ""))
                if last_event_id and task_manager:
                    events = task_manager.buffered_events(last_event_id)
                    if events:
                        replay["events"] = events
                if task_manager:
                    replay["pending_questions"] = interaction.pending_questions()
                    replay["running_tasks"] = task_manager.running_states()
                await conn.send_json({"op": "reconnect", **replay})
                continue

            # 未认证的请求直接拒绝
            if not conn.authenticated and op != "auth":
                await conn.send_json({"op": "error", "msg_id": msg_id,
                                      "detail": "未认证"})
                continue

            if dispatcher:
                await dispatcher.dispatch(conn, op, frame.get("data", {}) or {}, msg_id)

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await registry.remove(conn)
        # 连接断开时不取消任务（任务后台继续运行）
        # 仅清理连接相关资源
        try:
            await conn.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# 模块级单例（在 app.py 中初始化）
# --------------------------------------------------------------------------- #

_registry: ConnectionRegistry | None = None
_task_manager: ChatTaskManager | None = None
_dispatcher: OperationDispatcher | None = None


def init(auth_checker: Callable[[str], bool],
         logout_handler: Callable[[], None]) -> tuple[ConnectionRegistry, ChatTaskManager, OperationDispatcher]:
    """初始化模块级单例（由 app.py 在 startup 时调用）。"""
    global _registry, _task_manager, _dispatcher
    _registry = ConnectionRegistry()
    _task_manager = ChatTaskManager(_registry)
    _dispatcher = OperationDispatcher(_registry, _task_manager)
    _dispatcher._HANDLERS = _dispatcher._build_handlers()
    return _registry, _task_manager, _dispatcher


def get_registry() -> ConnectionRegistry | None:
    return _registry


def get_task_manager() -> ChatTaskManager | None:
    return _task_manager


def get_dispatcher() -> OperationDispatcher | None:
    return _dispatcher


def create_ws_endpoint():
    """返回 FastAPI WebSocket 路由函数（供 app.py 挂载）。"""

    async def ws_endpoint(websocket: WebSocket):
        await handle_connection(
            websocket,
            auth_checker=_auth_checker,
            logout_handler=_logout_handler,
            dispatcher=_dispatcher,
            task_manager=_task_manager,
            registry=_registry,
        )

    return ws_endpoint


# 由 app.py 注入的认证回调
_auth_checker: Callable[[str], bool] | None = None
_logout_handler: Callable[[], None] | None = None


def set_auth_callbacks(auth_checker: Callable[[str], bool],
                       logout_handler: Callable[[], None]) -> None:
    global _auth_checker, _logout_handler
    _auth_checker = auth_checker
    _logout_handler = logout_handler
