"""创建/管理当前会话的任务清单（todo list）。"""

from __future__ import annotations

import time
from typing import Any

NAME = "todo_write"
DESCRIPTION = "创建或更新当前会话的任务清单：跟踪任务进度，规划多步骤工作并随时调整"
PARAMETERS = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "description": "任务清单（全量提交）：相同 id 的条目会被更新，新条目追加；未列出的既有条目保留",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "任务唯一标识（更新既有任务时提供；新建可省略，自动生成）"},
                    "content": {"type": "string", "description": "任务内容，动词开头，清晰可执行"},
                    "status": {
                        "type": "string",
                        "description": "pending=未开始；in_progress=进行中；completed=已完成；cancelled=已取消",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                    },
                },
                "required": ["content", "status"],
            },
        },
    },
    "required": ["todos"],
}

VALID_STATUS = {"pending", "in_progress", "completed", "cancelled"}
STATUS_LABEL = {"pending": "未开始", "in_progress": "进行中", "completed": "已完成", "cancelled": "已取消"}
STATUS_MARK = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]", "cancelled": "[-]"}

_TODOS: list[dict[str, Any]] = []


def _render() -> str:
    if not _TODOS:
        return "（清单为空）"
    lines = []
    for item in _TODOS:
        mark = STATUS_MARK.get(item["status"], "[ ]")
        lines.append(f"{mark} #{item['id']} {item['content']}（{STATUS_LABEL.get(item['status'], item['status'])}）")
    counts: dict[str, int] = {}
    for item in _TODOS:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    summary = " · ".join(f"{STATUS_LABEL[k]} {v}" for k, v in sorted(counts.items()))
    return "\n".join(lines) + f"\n\n共 {len(_TODOS)} 项：{summary}"


def run(todos: list[dict]) -> dict:
    if not isinstance(todos, list) or not todos:
        return {"ok": False, "output": "todos 不能为空（至少 1 条任务）"}

    by_id = {item.get("id"): item for item in _TODOS if item.get("id")}
    for raw in todos:
        if not isinstance(raw, dict):
            return {"ok": False, "output": f"任务条目格式不正确: {raw!r}"}
        content = str(raw.get("content", "") or "").strip()
        status = str(raw.get("status", "pending") or "pending").strip()
        if not content:
            return {"ok": False, "output": "任务 content 不能为空"}
        if status not in VALID_STATUS:
            return {"ok": False, "output": f"未知 status: {status}（可选 pending/in_progress/completed/cancelled）"}
        tid = str(raw.get("id") or "").strip()
        if tid and tid in by_id:
            item = by_id[tid]
            item["content"] = content
            item["status"] = status
            item["updated_at"] = time.time()
        else:
            tid = tid or f"t{len(_TODOS) + 1}_{int(time.time() * 1000) % 100000}"
            item = {"id": tid, "content": content, "status": status,
                    "created_at": time.time(), "updated_at": time.time()}
            by_id[tid] = item
            _TODOS.append(item)

    return {"output": f"任务清单已更新（{len(_TODOS)} 项）：\n{_render()}"}


def snapshot() -> list[dict]:
    return [dict(item) for item in _TODOS]


def reset() -> None:
    _TODOS.clear()


__all__ = ["run", "snapshot", "reset", "NAME", "DESCRIPTION", "PARAMETERS"]
