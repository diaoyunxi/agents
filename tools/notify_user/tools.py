"""向用户发送一条进度/通知消息（正文回显；不挂起）。"""

from __future__ import annotations

NAME = "notify_user"
DESCRIPTION = "向用户发送一条进度/通知（不打断流程）：适合长任务里的里程碑播报"
PARAMETERS = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "要展示给用户的简短通知"},
        "level": {"type": "string", "description": "info/progress/warning/done，默认 info",
                  "enum": ["info", "progress", "warning", "done"]},
    },
    "required": ["message"],
}


def run(message: str, level: str = "info") -> dict:
    message = (message or "").strip()
    if not message:
        return {"ok": False, "output": "message 不能为空"}
    mark = {"info": "·", "progress": "▶", "warning": "⚠", "done": "✔"}.get((level or "info"), "·")
    # 直接回显即可（正文协议会把该输出呈现给用户）；无需挂起
    return {"output": f"{mark} {message}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
