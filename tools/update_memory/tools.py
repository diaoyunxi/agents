"""持久化记忆：写入 / 更新 / 删除知识条目（JSON 文件落盘）。"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from config import BASE_DIR

NAME = "update_memory"
DESCRIPTION = "写入、更新或删除持久化记忆（跨会话保留的知识库，存于项目 .memory/knowledge.json）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "create=新建记忆；update=更新既有记忆；delete=删除既有记忆",
            "enum": ["create", "update", "delete"],
        },
        "title": {"type": "string", "description": "简短标题，概括这条记忆（create/update 用）"},
        "knowledge_to_store": {"type": "string", "description": "要记住的具体内容，一段话以内（create/update 用）"},
        "existing_knowledge_id": {"type": "string", "description": "既有记忆的 ID（update/delete 必填）"},
    },
    "required": ["action"],
}

STORE_PATH = BASE_DIR / ".memory" / "knowledge.json"


def _load() -> list[dict[str, Any]]:
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    return [i for i in items if isinstance(i, dict) and i.get("id")] if isinstance(items, list) else []


def _save(items: list[dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


def _render(items: list[dict[str, Any]]) -> str:
    if not items:
        return "（记忆库为空）"
    lines = []
    for item in items:
        stamp = time.strftime("%Y-%m-%d", time.localtime(item.get("updated_at") or 0))
        lines.append(f"- [{item['id']}] {item.get('title', '（无题）')}（{stamp}）: {item.get('knowledge', '')}")
    return "\n".join(lines)


def run(action: str, title: str = "", knowledge_to_store: str = "", existing_knowledge_id: str = "") -> dict:
    action = (action or "").strip().lower()
    if action not in ("create", "update", "delete"):
        return {"ok": False, "output": f"未知 action: {action}（可选 create/update/delete）"}

    items = _load()
    kid = (existing_knowledge_id or "").strip()
    now = time.time()

    if action == "create":
        if not (knowledge_to_store or "").strip():
            return {"ok": False, "output": "create 需要提供 knowledge_to_store"}
        new_id = "mem_" + uuid.uuid4().hex[:8]
        items.append({
            "id": new_id,
            "title": (title or "").strip() or (knowledge_to_store.strip()[:20] + "…"),
            "knowledge": knowledge_to_store.strip(),
            "created_at": now,
            "updated_at": now,
        })
        _save(items)
        return {"output": f"已创建记忆 [{new_id}]。当前记忆库（{len(items)} 条）：\n{_render(items)}"}

    target = next((i for i in items if i["id"] == kid), None)
    if target is None:
        return {"ok": False, "output": (
            f"找不到 ID 为 `{kid}` 的记忆。{action} 操作必须提供 existing_knowledge_id。"
            f"当前记忆库（{len(items)} 条）：\n{_render(items)}")}

    if action == "delete":
        items = [i for i in items if i["id"] != kid]
        _save(items)
        return {"output": f"已删除记忆 [{kid}]。当前记忆库（{len(items)} 条）：\n{_render(items)}"}

    if not (knowledge_to_store or "").strip():
        return {"ok": False, "output": "update 需要提供 knowledge_to_store"}
    target["knowledge"] = knowledge_to_store.strip()
    if (title or "").strip():
        target["title"] = title.strip()
    target["updated_at"] = now
    _save(items)
    return {"output": f"已更新记忆 [{kid}]。当前记忆库（{len(items)} 条）：\n{_render(items)}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
