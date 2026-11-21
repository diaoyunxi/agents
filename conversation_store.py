"""对话持久化：管理 chat/ 目录下的 JSON 对话文件。

后端直接读写，替代原先由前端维护 history 数组 + 定期 PUT 保存的模式。
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

CHAT_DIR = Path(__file__).resolve().parent / "chat"


def _chat_dir() -> Path:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR


def _conv_path(cid: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(cid))
    if not safe:
        raise ValueError("非法的对话 ID")
    return _chat_dir() / f"{safe}.json"


def create(cid: str = "", title: str = "新对话", workspace: str = "") -> dict:
    """新建对话并落盘，返回对话字典。"""
    cid = str(cid or secrets.token_hex(8))
    _conv_path(cid)  # 校验合法性
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    conv = {
        "id": cid,
        "title": str(title).strip() or "新对话",
        "workspace": str(workspace or "").strip(),
        "created_at": stamp,
        "updated_at": stamp,
        "messages": [],
    }
    path = _conv_path(cid)
    path.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    return conv


def get(cid: str) -> dict | None:
    """读取对话；不存在返回 None。"""
    try:
        path = _conv_path(cid)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save(conv: dict) -> dict:
    """整体写回对话（更新 title / workspace / messages / updated_at）。"""
    cid = str(conv.get("id", ""))
    path = _conv_path(cid)
    if "title" in conv:
        conv["title"] = str(conv["title"]).strip() or conv.get("title", "新对话")
    if "workspace" in conv:
        conv["workspace"] = str(conv.get("workspace") or "").strip()
    if "messages" in conv:
        # 规范化消息：保留 user/assistant 角色与 tool_calls / tool_results
        new_msgs = []
        for m in (conv["messages"] or []):
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            entry = {"role": role, "content": str(m.get("content", ""))}
            if m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
            if m.get("tool_results"):
                entry["tool_results"] = m["tool_results"]
            new_msgs.append(entry)
        conv["messages"] = new_msgs
    conv["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    return conv


def list_conversations() -> list[dict]:
    """列出所有对话，按更新时间倒序。"""
    items = []
    for p in sorted(_chat_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append({
            "id": data.get("id", p.stem),
            "title": data.get("title", "未命名对话"),
            "workspace": data.get("workspace", ""),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "message_count": len(data.get("messages", [])),
        })
    return items


def delete(cid: str) -> bool:
    """删除对话文件；返回是否存在过。"""
    try:
        path = _conv_path(cid)
    except ValueError:
        return False
    if path.exists():
        path.unlink()
        return True
    return False
