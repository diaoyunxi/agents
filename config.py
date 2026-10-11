#!/usr/bin/env python3
"""全局配置中心：负责 config.json 的加载、保存、内存缓存与变更监听。

所有 AI 提供商、工具调用限制、MCP 服务器等配置都保存在 config.json，
程序启动时读取，运行期间若文件被外部修改（或通过 API 修改），会自动热加载。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Iterator

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
BACKUP_DIR = BASE_DIR / ".config_backups"

DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 6573, "workspace": "."},
    "auth": {
        "enabled": True,
        "username": "root",
        "password": "root",
        "setup_done": False,
    },
    "ai": {
        "active_provider_id": "",
        "active_model": "",
        "max_tokens": 8192,
        "temperature": 0.7,
        "timeout": 180,
        "use_function_calling": True,
    },
    "providers": [],
    "tool_limits": {
        "enabled": True,
        "max_calls_per_round": 10,
        "max_total_calls": 60,
        "max_rounds": 25,
        "denied_tools": [],
        "allowed_tools": [],
        "require_confirmation": [],
    },
    "mcp_servers": [],
    "ui": {"theme": "dark"},
}

_lock = threading.RLock()
_cache: dict[str, Any] = {}
_cache_mtime: float = 0.0
_listeners: list[Callable[[dict[str, Any]], None]] = []

# 对话级工作区覆盖：为空表示使用 config.json 中的默认工作区
_workspace_override: ContextVar[Path | None] = ContextVar("workspace_override", default=None)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _notify(config: dict[str, Any]) -> None:
    for cb in list(_listeners):
        try:
            cb(config)
        except Exception as exc:  # noqa: BLE001
            print(f"[config] listener error: {exc}")


def on_change(callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
    """注册配置变更回调，返回取消注册的函数。"""

    def _remove() -> None:
        with _lock:
            if callback in _listeners:
                _listeners.remove(callback)

    with _lock:
        _listeners.append(callback)
    return _remove


def _backup() -> None:
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"config-{stamp}.json")
        backups = sorted(BACKUP_DIR.glob("config-*.json"))
        for old in backups[:-20]:
            old.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def load(force: bool = False) -> dict[str, Any]:
    """读取配置；默认带 mtime 缓存检测，实现外部修改热加载。"""

    global _cache, _cache_mtime
    with _lock:
        if not CONFIG_PATH.exists():
            save(DEFAULT_CONFIG)
            return _cache
        try:
            mtime = CONFIG_PATH.stat().st_mtime
        except OSError:
            return _cache
        if not force and _cache and abs(mtime - _cache_mtime) < 1e-6:
            return _cache
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[config] 解析失败，沿用上次配置: {exc}")
            return _cache
        config = _deep_merge(DEFAULT_CONFIG, raw)
        changed = json.dumps(config, sort_keys=True) != json.dumps(_cache, sort_keys=True)
        _cache = config
        _cache_mtime = mtime
        if changed and _listeners:
            _notify(config)
        return _cache


def save(config: dict[str, Any]) -> dict[str, Any]:
    global _cache, _cache_mtime
    with _lock:
        merged = _deep_merge(DEFAULT_CONFIG, config or {})
        if CONFIG_PATH.exists():
            _backup()
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, CONFIG_PATH)
        _cache = merged
        _cache_mtime = CONFIG_PATH.stat().st_mtime
        _notify(merged)
        return _cache


def update(mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """以函数式方式局部更新配置并落盘。"""

    with _lock:
        current = load(force=True)
        draft = json.loads(json.dumps(current))
        mutator(draft)
        return save(draft)


def get(path: str, default: Any = None) -> Any:
    """按 "a.b.c" 路径读取配置值。"""

    node: Any = load()
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def set_value(path: str, value: Any) -> dict[str, Any]:
    parts = path.split(".")

    def _mutate(cfg: dict[str, Any]) -> None:
        node = cfg
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    return update(_mutate)


def resolve_workspace(path: str | Path | None = None) -> Path:
    """把工作区路径解析为绝对路径；相对路径基于程序目录。"""

    raw = str(path).strip() if path is not None else ""
    ws = Path(raw or ".")
    if not ws.is_absolute():
        ws = (BASE_DIR / ws).resolve()
    return ws


def workspace_dir() -> Path:
    """返回当前生效的工作区；对话进行中可能被 use_workspace 临时覆盖。"""

    override = _workspace_override.get()
    ws = override if override is not None else resolve_workspace(get("server.workspace", "."))
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@contextmanager
def use_workspace(path: str | Path | None = None) -> Iterator[Path]:
    """在上下文内把工作区切换为 path（空值表示沿用默认工作区）。

    仅影响当前请求的任务上下文，多个对话互不干扰。
    """

    raw = "" if path is None else str(path).strip()
    if not raw:
        yield workspace_dir()
        return
    resolved = resolve_workspace(raw)
    resolved.mkdir(parents=True, exist_ok=True)
    token = _workspace_override.set(resolved)
    try:
        yield resolved
    finally:
        _workspace_override.reset(token)


def tools_dir() -> Path:
    return BASE_DIR / "tools"


def skills_dir() -> Path:
    return BASE_DIR / "skills"


def start_watcher(interval: float = 2.0) -> threading.Thread:
    """后台轮询 config.json 的 mtime，实现外部修改热加载。"""

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                load()
            except Exception:  # noqa: BLE001
                pass

    thread = threading.Thread(target=_loop, name="config-watcher", daemon=True)
    thread.start()
    return thread


def public_config(include_secrets: bool = False) -> dict[str, Any]:
    """给前端使用的配置视图，可选择隐藏 api_key。"""

    config = json.loads(json.dumps(load()))
    if not include_secrets:
        for provider in config.get("providers", []):
            if provider.get("api_key"):
                provider["api_key"] = ""
                provider["has_api_key"] = True
    for server in config.get("mcp_servers", []):
        server.pop("env", None)
        for item in server.get("headers", {}).keys():
            server["headers"][item] = "***"
    config["auth"].pop("password", None)
    return config
