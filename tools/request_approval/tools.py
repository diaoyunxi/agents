"""高风险操作的人工审批门控：发起审批请求并挂起等待用户 批准 / 拒绝。

复用 interaction 的挂起机制：工具返回带 `question` 的结果时，运行时会推送问题卡片
并挂起等待用户点击；用户选择后回灌为文本（见 agent_runtime._ask_and_wait）。
"""

from __future__ import annotations

import interaction

NAME = "request_approval"
DESCRIPTION = "对高风险操作发起人工审批：说明拟执行的动作与风险，挂起等待用户 批准/拒绝；未获批准不得执行"
PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "description": "拟执行的高风险动作的完整描述（改什么、影响什么、是否可回滚）"},
        "risk": {"type": "string", "description": "风险级别：low/medium/high/critical，默认 high",
                  "enum": ["low", "medium", "high", "critical"]},
        "context": {"type": "string", "description": "补充背景，帮助用户判断（可选）"},
        "timeout": {"type": "integer", "description": "等待审批的最长秒数，默认 300，最大 3600"},
    },
    "required": ["action"],
}


def run(action: str, risk: str = "high", context: str = "", timeout: int = 300) -> dict:
    action = (action or "").strip()
    if not action:
        return {"ok": False, "output": "action 不能为空"}
    risk = (risk or "high").strip().lower()
    if risk not in ("low", "medium", "high", "critical"):
        risk = "high"
    timeout = max(10, min(int(timeout or 300), 3600))

    label = f"[审批 · {risk} 风险] {action}"
    if context:
        label += f"\n背景: {context}"

    qid = interaction.create_question(
        label,
        [{"label": "批准，执行", "description": "允许按描述执行该操作"},
         {"label": "拒绝", "description": "取消该操作，不要执行"}],
        multi_select=False,
    )

    return {
        "ok": True,
        "output": f"已发起审批（{qid}）：{action}\n等待用户 批准/拒绝……",
        "question": {"id": qid, "question": label,
                     "options": [{"label": "批准，执行"}, {"label": "拒绝"}],
                     "multi_select": False, "timeout": timeout},
    }


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
