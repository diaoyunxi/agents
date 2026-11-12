"""紧急停止：用户或运行时的最高优先级停止信号（比 stop 更强，立即中止并保留说明）。"""

from __future__ import annotations

from typing import Any

NAME = "emergency_stop"
DESCRIPTION = "紧急停止当前任务（最高优先级）：立即中止后续所有步骤并保留停止说明；用于发现严重风险/用户要求叫停时"
PARAMETERS = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "description": "停止原因（为何紧急停止、发现了什么风险）"},
        "preserve_progress": {"type": "boolean", "description": "是否保留已完成的阶段性成果，默认 true"},
    },
    "required": ["reason"],
}


def run(reason: str, preserve_progress: bool = True) -> dict[str, Any]:
    note = (reason or "").strip()
    payload = {
        "ok": True,
        "stop_task": True,           # 复用运行时的 stop 识别机制：本轮交互结束
        "emergency": True,
        "preserve_progress": bool(preserve_progress),
        "reason": note,
        "output": "（emergency_stop 已触发）任务已紧急中止。原因: " + (note or "未说明"),
    }
    if preserve_progress:
        payload["output"] += "。已保留阶段性成果，请用户确认下一步。"
    return payload


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
