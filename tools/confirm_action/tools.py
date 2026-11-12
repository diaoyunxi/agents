"""不可逆操作的二次确认：让用户明确 确认/取消 后再继续。"""

from __future__ import annotations

import interaction

NAME = "confirm_action"
DESCRIPTION = "对不可逆操作做二次确认：向用户展示要点并等待 确认/取消；拒绝时不得执行该操作"
PARAMETERS = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "要向用户确认的操作说明（含将产生的影响）"},
        "confirm_label": {"type": "string", "description": "确认按钮文案，默认「确认执行」"},
        "timeout": {"type": "integer", "description": "等待确认的最长秒数，默认 300"},
    },
    "required": ["message"],
}


def run(message: str, confirm_label: str = "确认执行", timeout: int = 300) -> dict:
    message = (message or "").strip()
    if not message:
        return {"ok": False, "output": "message 不能为空"}
    timeout = max(10, min(int(timeout or 300), 3600))

    qid = interaction.create_question(
        message,
        [{"label": confirm_label or "确认执行"}, {"label": "取消"}],
        multi_select=False,
    )
    return {
        "ok": True,
        "output": f"已请求二次确认（{qid}）：{message[:120]}\n等待用户 确认/取消……",
        "question": {"id": qid, "question": message,
                     "options": [{"label": confirm_label or "确认执行"}, {"label": "取消"}],
                     "multi_select": False, "timeout": timeout},
    }


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
