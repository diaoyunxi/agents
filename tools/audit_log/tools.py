"""工具调用审计：把高风险/关键动作记入工作区审计日志（追加 JSONL）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from common import workspace_dir

NAME = "audit_log"
DESCRIPTION = "把一次工具调用/决策记入审计日志（.audit/audit.jsonl），用于事后追溯与合规"
PARAMETERS = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "description": "被审计的工具名"},
        "input_summary": {"type": "string", "description": "输入摘要（避免记录敏感明文，可脱敏）"},
        "output_summary": {"type": "string", "description": "输出摘要"},
        "decision": {"type": "string", "description": "决策说明（为何批准/拒绝/放行）"},
        "risk": {"type": "string", "description": "风险级别：low/medium/high/critical"},
    },
    "required": ["tool"],
}


def _log_path() -> Path:
    ws = workspace_dir().resolve()
    d = ws / ".audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / "audit.jsonl"


def run(tool: str, input_summary: str = "", output_summary: str = "",
        decision: str = "", risk: str = "low") -> dict:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": (tool or "").strip(),
        "input": (input_summary or "").strip()[:2000],
        "output": (output_summary or "").strip()[:2000],
        "decision": (decision or "").strip()[:2000],
        "risk": (risk or "low").strip().lower(),
    }
    path = _log_path()
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        return {"ok": False, "output": f"写入审计日志失败: {exc}"}
    return {"output": f"已记录审计: {entry['tool']}（risk={entry['risk']}）-> {path.name}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
