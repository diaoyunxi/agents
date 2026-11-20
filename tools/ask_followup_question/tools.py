"""向用户提出结构化选择题，并等待用户回答。"""

from __future__ import annotations

from typing import Any

import interaction

NAME = "ask_followup_question"
DESCRIPTION = "向用户提出结构化选择题（2-6 个选项），暂停并等待用户点击回答后继续"
PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "完整的问题描述，说清背景与你想确认什么"},
        "options": {
            "type": "array",
            "description": "可选项，2-6 个；每项为 {\"label\": \"选项文字\", \"description\": \"补充说明（可选）\"}",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "选项显示文字，简短明确"},
                    "description": {"type": "string", "description": "该选项的补充说明，可省略"},
                },
                "required": ["label"],
            },
        },
        "multiSelect": {"type": "boolean", "description": "是否允许多选，默认 false"},
        "timeout": {"type": "integer", "description": "等待用户回答的最长秒数，默认 600，最大 3600"},
    },
    "required": ["question", "options"],
}


def _normalize_options(raw: Any) -> tuple[list[dict], str]:
    if not isinstance(raw, list) or len(raw) < 2:
        return [], "options 至少需要 2 个选项"
    if len(raw) > 6:
        return [], "options 最多 6 个选项，请合并相近项"
    options: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            label, desc = item.strip(), ""
        elif isinstance(item, dict):
            label, desc = str(item.get("label", "")).strip(), str(item.get("description", "") or "").strip()
        else:
            return [], f"选项格式不正确: {item!r}（应为字符串或 {{\"label\":..., \"description\":...}}）"
        if not label:
            return [], "存在空选项 label"
        if label in seen:
            return [], f"选项重复: {label}"
        seen.add(label)
        options.append({"label": label, "description": desc})
    return options, ""


async def run(question: str, options: Any, multiSelect: bool = False, timeout: int = 600) -> dict:
    question = (question or "").strip()
    if not question:
        return {"ok": False, "output": "question 不能为空"}
    normalized, err = _normalize_options(options)
    if err:
        return {"ok": False, "output": err}
    timeout = max(10, min(int(timeout or 600), 3600))

    qid = interaction.create_question(question, normalized, bool(multiSelect))
    preview = " / ".join(o["label"] for o in normalized)
    return {
        "ok": True,
        "output": f"已向用户提问（{qid}）：{question}\n选项：{preview}\n等待用户回答……",
        "question": {"id": qid, "question": question, "options": normalized,
                     "multi_select": bool(multiSelect), "timeout": timeout},
    }


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
