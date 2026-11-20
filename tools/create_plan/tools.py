"""任务计划：创建/更新一个结构化执行计划（落盘工作区 .plan/），供多步骤推进与用户查看。"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from common import relative, workspace_dir

NAME = "create_plan"
DESCRIPTION = "为复杂任务创建一个结构化执行计划（步骤列表+目标），落盘供后续 update_plan 推进"
PARAMETERS = {
    "type": "object",
    "properties": {
        "goal": {"type": "string", "description": "一句话任务目标"},
        "steps": {
            "type": "array",
            "description": "有序步骤，每项 {\"desc\": \"做什么\", \"why\": \"为何（可选）\"}",
            "items": {
                "type": "object",
                "properties": {
                    "desc": {"type": "string", "description": "步骤描述（动词开头）"},
                    "why": {"type": "string", "description": "该步骤的意图/理由，可选"},
                },
                "required": ["desc"],
            },
        },
    },
    "required": ["goal", "steps"],
}


def _plan_path(plan_id: str | None = None) -> Path:
    d = workspace_dir().resolve() / ".plan"
    d.mkdir(parents=True, exist_ok=True)
    pid = plan_id or ("plan_" + uuid.uuid4().hex[:8])
    return d / f"{pid}.json"


def _load(plan_id: str) -> dict:
    data = json.loads(_plan_path(plan_id).read_text(encoding="utf-8"))
    return data


def _render(plan: dict) -> str:
    lines = [f"# 计划 {plan['id']}: {plan['goal']}", ""]
    counts = {}
    for i, step in enumerate(plan["steps"], 1):
        st = step.get("status", "pending")
        counts[st] = counts.get(st, 0) + 1
        mark = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "skipped": "[-]"}.get(st, "[ ]")
        line = f"{mark} {i}. {step['desc']}"
        if step.get("why"):
            line += f"（{step['why']}）"
        lines.append(line)
    summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    lines += ["", f"共 {len(plan['steps'])} 步：{summary}"]
    return "\n".join(lines)


def run(goal: str, steps: list) -> dict:
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "output": "goal 不能为空"}
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "output": "steps 不能为空"}
    for s in steps:
        if not isinstance(s, dict) or not str(s.get("desc", "")).strip():
            return {"ok": False, "output": "每个 step 需有非空 desc"}

    pid = "plan_" + uuid.uuid4().hex[:8]
    plan = {
        "id": pid, "goal": goal, "created_at": time.time(), "updated_at": time.time(),
        "steps": [dict(s, status=s.get("status", "pending")) for s in steps],
    }
    _plan_path(pid).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    out = f"已创建计划 {pid}（落盘 {relative(_plan_path(pid))}）：\n{_render(plan)}\n\n" \
          f"推进进度请用 update_plan(plan_id=\"{pid}\")。"
    return {"output": out}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
