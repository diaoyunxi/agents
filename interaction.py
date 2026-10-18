"""交互式提问桥接：ask_followup_question 工具（挂起等待）与 Web 端回答 API 之间的通道。

工具在事件循环里创建一个 Future 并挂起；前端渲染问题卡片，
用户点击选项后由 POST /api/question/{qid}/answer 调 resolve() 唤醒。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

# qid -> {future, question, options, multi_select, created_at, answer}
_PENDING: dict[str, dict[str, Any]] = {}
# 本次进程内所有提问记录（含已回答），便于排查
_LOG: list[dict[str, Any]] = []
EXPIRE_SECONDS = 3600


def create_question(question: str, options: list[dict], multi_select: bool = False) -> str:
    """登记一个新问题并返回 qid（必须在运行中的事件循环内调用）。"""

    qid = "q_" + uuid.uuid4().hex[:10]
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _PENDING[qid] = {
        "future": future,
        "question": question,
        "options": options,
        "multi_select": multi_select,
        "created_at": time.time(),
        "answer": None,
    }
    _LOG.append({"id": qid, "question": question, "time": time.time()})
    _gc()
    return qid


def resolve(qid: str, answer: Any) -> bool:
    """用户已回答；问题不存在或已结束时返回 False。"""

    item = _PENDING.get(qid)
    if item is None or item["future"].done():
        return False
    item["answer"] = answer
    item["future"].set_result(answer)
    return True


def get(qid: str) -> dict | None:
    item = _PENDING.get(qid)
    if not item:
        return None
    return {
        "id": qid,
        "question": item["question"],
        "options": item["options"],
        "multi_select": item["multi_select"],
        "answered": item["future"].done() and item["answer"] is not None,
    }


async def wait(qid: str, timeout: int = 600) -> str:
    """等待用户回答，返回答案文本；超时/失效时返回说明文本。"""

    item = _PENDING.get(qid)
    if item is None:
        return "（问题已失效，未能获得用户回答）"
    try:
        answer = await asyncio.wait_for(asyncio.shield(item["future"]), timeout=max(5, int(timeout)))
    except asyncio.TimeoutError:
        return f"（用户未在 {int(timeout)} 秒内回答，已按超时处理；请基于合理默认值继续，或在最终答复中说明假设）"
    except Exception as exc:  # noqa: BLE001
        return f"（等待回答出错: {exc}）"
    _PENDING.pop(qid, None)
    if isinstance(answer, list):
        return "、".join(str(a) for a in answer) if answer else "（用户未作出选择）"
    return str(answer)


def cancel_all(reason: str = "会话已结束") -> None:
    """对话终止时唤醒所有挂起的问题，避免工具永远挂起。"""

    for item in list(_PENDING.values()):
        if not item["future"].done():
            item["future"].set_result(f"（{reason}，未获得回答）")
    _PENDING.clear()


def _gc() -> None:
    now = time.time()
    for qid, item in list(_PENDING.items()):
        if now - item["created_at"] > EXPIRE_SECONDS:
            if not item["future"].done():
                item["future"].set_result("（问题已过期）")
            _PENDING.pop(qid, None)


__all__ = ["create_question", "resolve", "get", "wait", "cancel_all"]
