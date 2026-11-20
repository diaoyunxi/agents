"""团队模式消息通道：向队友发送消息 / 广播 / 控制类协议消息。"""

from __future__ import annotations

import time
from typing import Any

NAME = "send_message"
DESCRIPTION = "团队模式下向队友发送消息、广播或协议消息（shutdown/plan_approval 等）；当前无注册队友时记录到本地会话日志"
PARAMETERS = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "description": "消息类型",
            "enum": ["message", "broadcast", "shutdown_request", "shutdown_response", "plan_approval_response"],
        },
        "recipient": {"type": "string", "description": "接收方队友名称（type=message 时必填；broadcast 时忽略）"},
        "content": {"type": "string", "description": "消息正文"},
        "summary": {"type": "string", "description": "一句话摘要（5-10 词），用于列表展示"},
    },
    "required": ["type", "content"],
}

MESSAGE_TYPES = ("message", "broadcast", "shutdown_request", "shutdown_response", "plan_approval_response")

# 队友注册表：name -> 待处理消息列表（团队模式激活时由运行时登记）
_TEAMMATES: dict[str, list[dict[str, Any]]] = {}
# 本次会话发出的全部消息
_LOG: list[dict[str, Any]] = []


def register_teammate(name: str) -> None:
    name = (name or "").strip()
    if name:
        _TEAMMATES.setdefault(name, [])


def unregister_teammate(name: str) -> None:
    _TEAMMATES.pop((name or "").strip(), None)


def inbox(name: str) -> list[dict[str, Any]]:
    return list(_TEAMMATES.get((name or "").strip(), []))


def sent_log() -> list[dict[str, Any]]:
    return list(_LOG)


def run(type: str = "message", recipient: str = "", content: str = "", summary: str = "") -> dict:
    mtype = (type or "message").strip()
    if mtype not in MESSAGE_TYPES:
        return {"ok": False, "output": f"未知消息类型: {type}（可选 {', '.join(MESSAGE_TYPES)}）"}
    if not (content or "").strip():
        return {"ok": False, "output": "content 不能为空"}

    recipient = (recipient or "").strip()
    entry = {
        "type": mtype,
        "from": "main",
        "to": recipient or "(all)",
        "content": content.strip(),
        "summary": (summary or "").strip() or content.strip()[:40],
        "time": time.strftime("%H:%M:%S"),
    }
    _LOG.append(entry)

    if mtype == "broadcast":
        if not _TEAMMATES:
            return {"ok": True, "output":
                    f"广播已记录，但当前没有活跃队友（团队模式未启用）。摘要: {entry['summary']}"}
        for name in _TEAMMATES:
            _TEAMMATES[name].append(entry)
        return {"ok": True, "output":
                f"已广播给 {len(_TEAMMATES)} 个队友（{', '.join(_TEAMMATES)}）。摘要: {entry['summary']}"}

    if not recipient:
        return {"ok": False, "output": f"type={mtype} 时必须提供 recipient（队友名称）"}

    if recipient not in _TEAMMATES:
        known = ", ".join(_TEAMMATES) if _TEAMMATES else "无"
        return {"ok": True, "output": (
            f"消息已记录到本地会话日志，但队友 `{recipient}` 未注册/不在线，无法真正送达。"
            f"当前已注册队友：{known}。（团队模式未启用时消息仅作记录）")}

    _TEAMMATES[recipient].append(entry)
    pending = len(_TEAMMATES[recipient])
    return {"ok": True, "output": f"已发送给 {recipient}（{mtype}），其待处理消息 {pending} 条。摘要: {entry['summary']}"}


__all__ = ["run", "register_teammate", "unregister_teammate", "inbox", "sent_log",
           "NAME", "DESCRIPTION", "PARAMETERS"]
