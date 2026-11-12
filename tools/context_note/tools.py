"""上下文沉淀：把长任务中的关键事实/决策/状态落盘（.context/），供后续轮次跨会话引用。"""

from __future__ import annotations

import time
from pathlib import Path

from common import relative, workspace_dir

NAME = "context_note"
DESCRIPTION = "把关键事实/决策/中间状态沉淀到工作区 .context/notes.md（长任务跨轮引用，对抗上下文遗忘）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "fact": {"type": "string", "description": "要记住的关键事实/决策/结论（一句到几句）"},
        "category": {"type": "string", "description": "分类标签，如 decision / fact / state / open_issue"},
        "review": {"type": "boolean", "description": "设为 true 时只回读当前沉淀内容，不写入"},
    },
    "required": ["fact"],
}


def _path() -> Path:
    d = workspace_dir().resolve() / ".context"
    d.mkdir(parents=True, exist_ok=True)
    return d / "notes.md"


def run(fact: str, category: str = "", review: bool = False) -> dict:
    p = _path()
    if review:
        if not p.exists() or not p.read_text(encoding="utf-8").strip():
            return {"output": "（暂无沉淀的上下文）"}
        return {"output": "当前沉淀的上下文：\n" + p.read_text(encoding="utf-8")[:5000]}

    fact = (fact or "").strip()
    if not fact:
        return {"ok": False, "output": "fact 不能为空（或用 review=true 回读）"}
    cat = (category or "").strip()
    stamp = time.strftime("%H:%M:%S")
    line = f"- [{stamp}]" + (f" <{cat}>" if cat else "") + f" {fact}\n"

    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    p.write_text((existing.rstrip() + "\n" + line if existing.strip() else line), encoding="utf-8")
    count = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("- ["))
    return {"output": f"已沉淀上下文（{relative(p)}，共 {count} 条）。可用 context_note(review=true) 回读。"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
