"""MCP 接入层：连接 config.json 中配置的 MCP Server，并把它们的工具纳入工具清单。"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

import config

_connections: dict = {}
_lock = asyncio.Lock()


def _server_id(cfg: dict) -> str:
    return cfg.get("id") or "{}::{}".format(cfg.get("name", "mcp"), cfg.get("command", ""))


def _enabled_servers() -> list:
    return [s for s in (config.get("mcp_servers") or []) if s.get("enabled", True)]


def _params(server: dict):
    from mcp import StdioServerParameters

    env = dict(server.get("env") or {})
    return StdioServerParameters(
        command=server.get("command", ""),
        args=server.get("args") or [],
        env=env or None,
        cwd=server.get("cwd") or None,
    )


async def _connect(server: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    sid = _server_id(server)
    entry = _connections.get(sid)
    if entry and not entry.get("closed"):
        return entry

    async with _lock:
        entry = _connections.get(sid)
        if entry and not entry.get("closed"):
            return entry
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(_params(server)))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception as exc:  # noqa: BLE001
            await stack.aclose()
            _connections[sid] = {"closed": True, "error": str(exc), "tools": []}
            return _connections[sid]
        entry = {"stack": stack, "session": session, "tools": [], "closed": False, "error": ""}
        _connections[sid] = entry

    try:
        listing = await entry["session"].list_tools()
        entry["tools"] = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": getattr(t, "inputSchema", None) or {"type": "object", "properties": {}},
            }
            for t in listing.tools
        ]
    except Exception as exc:  # noqa: BLE001
        entry["error"] = str(exc)
    return entry


def schema_to_doc(name: str, description: str, schema: dict) -> str:
    """把 MCP 工具的 JSON Schema 转成与内置 tools.md 一致的自然语言说明。"""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    lines = ["## 作用", description or f"MCP 服务器提供的工具 `{name}`。", "", "## 参数"]
    if not props:
        lines.append("- （无参数，直接把 arguments 留空对象）")
    for key, spec in props.items():
        typ = spec.get("type", "string")
        if typ == "array" and isinstance(spec.get("items"), dict):
            typ = "array<{}>".format(spec["items"].get("type", "string"))
        flag = "必填" if key in required else "可选"
        desc = spec.get("description") or spec.get("title") or ""
        if spec.get("enum"):
            desc = (desc + " 可选值: " + ", ".join(str(e) for e in spec["enum"])).strip()
        lines.append(f"- {key} ({typ}, {flag}): {desc}")
    return "\n".join(lines)


def prefixed(server_name: str, tool_name: str) -> str:
    return f"mcp__{server_name}__{tool_name}"


async def list_all_tools() -> list:
    """返回所有已连接 MCP 服务器的工具。"""
    results = []
    for server in _enabled_servers():
        entry = await _connect(server)
        server_name = server.get("name") or _server_id(server)
        for tool in entry.get("tools", []):
            full = prefixed(server_name, tool["name"])
            results.append({
                "name": full,
                "mcp_server": server_name,
                "raw_name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
                "doc": schema_to_doc(tool["name"], tool["description"], tool["input_schema"]),
                "error": entry.get("error", ""),
            })
    return results


async def call_tool(full_name: str, arguments: dict) -> dict:
    """按 mcp__server__tool 的名称调用 MCP 工具。"""
    parts = full_name.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return {"ok": False, "output": "不是合法的 MCP 工具名: " + full_name}
    server_name, raw_name = parts[1], "__".join(parts[2:])
    server = next((s for s in _enabled_servers() if (s.get("name") or _server_id(s)) == server_name), None)
    if server is None:
        return {"ok": False, "output": "未找到 MCP 服务器: " + server_name}
    entry = await _connect(server)
    if entry.get("closed"):
        return {"ok": False, "output": "MCP 服务器连接失败: " + (entry.get("error") or "未知错误")}
    try:
        result = await entry["session"].call_tool(raw_name, arguments or {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": "MCP 工具调用失败: " + str(exc)}
    chunks = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
        elif getattr(item, "type", "") == "resource":
            chunks.append(str(getattr(item, "resource", "")))
    output = "\n".join(chunks) or "(无输出)"
    return {"ok": not getattr(result, "isError", False), "output": output}


_prompt_cache = {"text": "", "stamp": 0.0}


def mcp_prompt_section() -> str:
    """MCP 工具说明章节（同步版本，读取上次刷新结果）。"""
    return _prompt_cache.get("text", "")


async def refresh_prompt() -> str:
    """连接全部 MCP 服务器并重建提示词章节。"""
    import time

    tools = await list_all_tools()
    if not tools:
        _prompt_cache.update({"text": "", "stamp": time.time()})
        return ""
    chunks = [
        ("# MCP 工具\n\n以下工具由外部 MCP 服务器提供，调用方式与内置工具完全相同。\n"
        "工具名格式为 mcp__服务器名__工具名，例如 mcp__filesystem__read_file。")
    ]
    for tool in tools:
        head = "### 工具 `{}` —— 来自 MCP 服务器 `{}`".format(tool["name"], tool["mcp_server"])
        chunks.append(head + "\n" + tool["doc"])
    text = "\n\n".join(chunks)
    _prompt_cache.update({"text": text, "stamp": time.time()})
    return text


async def status() -> list:
    out = []
    for server in config.get("mcp_servers") or []:
        if not server.get("enabled", True):
            out.append({"name": server.get("name"), "enabled": False, "tools": 0, "error": "已禁用"})
            continue
        entry = await _connect(server)
        out.append({
            "id": _server_id(server),
            "name": server.get("name") or _server_id(server),
            "command": server.get("command"),
            "args": server.get("args") or [],
            "enabled": True,
            "connected": not entry.get("closed"),
            "tools": len(entry.get("tools") or []),
            "error": entry.get("error", ""),
        })
    return out


async def close_all() -> None:
    for sid, entry in list(_connections.items()):
        if entry.get("stack"):
            try:
                await entry["stack"].aclose()
            except Exception:  # noqa: BLE001
                pass
        _connections[sid] = {"closed": True, "tools": [], "error": ""}
