"""更新既有计划：改步骤状态 / 追加步骤 / 修订描述（落盘 .plan/）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from common import relative, workspace_dir

NAME = "update_plan"
DESCRIPTION = "更新 create_plan 生成的计划：置步骤状态、追加步骤、修订描述；并回显最新计划"
PARAMETERS = {
    "type": "object",
    "properties": {
        "plan_id": {"type": "string", "description": "计划 ID（create_plan 返回的）"},
        "step_index": {"type": "integer", "description": "要更新状态的步骤序号（0 起）；配合 status"},
        "status": {"type": "string", "description": "置为：pending/in_progress/done/skipped",
                   "enum": ["pending", "in_progress", "done", "skipped"]},
        "add_step": {"type": "string", "description": "追加一个新步骤（desc）"},
        "note": {"type": "string", "description": "在计划末尾追加一条进度备注"},
    },
    "required": ["plan_id"],
}

VALID = {"pending", "in_progress", "done", "skipped"}


def _plan_path(plan_id: str) -> Path:
    return workspace_dir().resolve() / ".plan" / f"{plan_id}.json"


def _render(plan: dict) -> str:
    lines = [f"# 计划 {plan['id']}: {plan['goal']}", ""]
    for i, step in enumerate(plan["steps"], 1):
        st = step.get("status", "pending")
        mark = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "skipped": "[-]"}.get(st, "[ ]")
        line = f"{mark} {i}. {step['desc']}"
        if step.get("note"):
            line += f" —— {step['note']}"
        lines.append(line)
    for note in plan.get("notes", []):
        lines.append(f"· {note}")
    return "\n".join(lines)


def run(plan_id: str, step_index: int = 0, status: str = "", add_step: str = "", note: str = "") -> dict:
    path = _plan_path(plan_id)
    if not path.exists():
        return {"ok": False, "output": f"找不到计划 {plan_id}（.plan/{plan_id}.json 不存在）"}
    plan = json.loads(path.read_text(encoding="utf-8"))

    if status:
        if status not in VALID:
            return {"ok": False, "output": f"未知 status: {status}"}
        idx = int(step_index or 0)
        if 0 <= idx < len(plan["steps"]):
            plan["steps"][idx]["status"] = status
        else:
            return {"ok": False, "output": f"step_index {idx} 越界（计划共 {len(plan['steps'])} 步）"}
    if add_step:
        plan["steps"].append({"desc": add_step.strip(), "status": "pending"})
    if note:
        plan.setdefault("notes", []).append(note.strip())

    plan["updated_at"] = time.time()
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": f"计划 {plan_id} 已更新：\n{_render(plan)}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
