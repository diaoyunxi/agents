"""结构化思考/推理暂存：把多步推理写入工作区临时文件，供后续步骤与用户查看。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from common import workspace_dir

NAME = "think"
DESCRIPTION = "把一段结构化推理/假设/权衡暂存到工作区（.think/），便于长任务中沉淀思考并供后续步骤引用"
PARAMETERS = {
    "type": "object",
    "properties": {
        "thought": {"type": "string", "description": "要暂存的思考内容（假设、推理、权衡、风险）"},
        "topic": {"type": "string", "description": "可选：这条思考属于哪个主题/步骤"},
        "review": {"type": "boolean", "description": "设为 true 时只回读最近一条，不写入（用于复核）"},
    },
    "required": ["thought"],
}


def _dir() -> Path:
    d = workspace_dir().resolve() / ".think"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(thought: str, topic: str = "", review: bool = False) -> dict:
    d = _dir()
    if review:
        files = sorted(d.glob("*.md"))
        if not files:
            return {"output": "（暂无暂存的思考）"}
        last = files[-1]
        return {"output": f"最近一条暂存思考（{last.name}）：\n{last.read_text(encoding='utf-8')[:3000]}"}

    thought = (thought or "").strip()
    if not thought:
        return {"ok": False, "output": "thought 不能为空（或用 review=true 回读）"}
    fname = f"{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}.md"
    body = (f"## {topic or '思考'}\n\n" if topic else "") + thought + "\n"
    (d / fname).write_text(body, encoding="utf-8")
    total = len(list(d.glob("*.md")))
    return {"output": f"已暂存思考 {fname}（第 {total} 条）。后续步骤可用 think(review=true) 复核。"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
