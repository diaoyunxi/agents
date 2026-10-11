"""特殊控制工具：stop。

这是一个信号型工具，AI 仅在确实希望结束当前任务时才调用它。
运行时检测到该调用后会停止后续交互；若 AI 没有调用任何工具（也即没有调用 stop），
运行时会反向要求 AI 继续推进，而不是直接结束。
"""

from __future__ import annotations

from typing import Any

NAME = "stop"
DESCRIPTION = "信号工具：AI 明确请求结束当前任务（不执行任何副作用）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "description": "可选，停止原因/一句话总结，会回显给用户"},
    },
    "required": [],
}


def run(reason: str | None = None) -> dict[str, Any]:
    """不执行副作用，仅返回一个 stop_task 标记，交由运行时识别。"""
    note = (reason or "").strip() if isinstance(reason, str) else ""
    return {
        "ok": True,
        "stop_task": True,
        "reason": note,
        "output": "（stop 已收到）任务结束请求。" + (f" 说明: {note}" if note else ""),
    }


__all__ = ["DESCRIPTION", "NAME", "PARAMETERS", "run"]
