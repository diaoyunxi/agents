"""轻量知识库：SQLite 存储 + 关键词检索（免外部向量库，可按需升级 FTS/向量）。"""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from pathlib import Path

from common import workspace_dir

NAME = "knowledge_base_search"
DESCRIPTION = "对本地知识库做关键词检索/写入（SQLite，存于 .kb/kb.sqlite）；支持 add/search/list/delete"
PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "description": "add=写入条目；search=检索；list=列出；delete=删除",
                    "enum": ["add", "search", "list", "delete"]},
        "query": {"type": "string", "description": "search 用：关键词（空格分词）"},
        "title": {"type": "string", "description": "add 用：条目标题"},
        "content": {"type": "string", "description": "add 用：正文"},
        "tags": {"type": "string", "description": "add 用：逗号分隔的标签"},
        "id": {"type": "string", "description": "delete 用：条目 ID"},
        "limit": {"type": "integer", "description": "search/list 最多返回条数，默认 10"},
    },
    "required": ["action"],
}

_TOKEN = re.compile(r"[\u4e00-\u9fff]|[a-z0-9_]+", re.IGNORECASE)


def _db() -> tuple[Path, sqlite3.Connection]:
    d = workspace_dir().resolve() / ".kb"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "kb.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS kb (id TEXT PRIMARY KEY, title TEXT, content TEXT, "
                 "tags TEXT, created_at REAL)")
    return path, conn


def _tokens(s: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(s or "")]


def run(action: str, query: str = "", title: str = "", content: str = "",
        tags: str = "", id: str = "", limit: int = 10) -> dict:
    act = (action or "").strip().lower()
    path, conn = _db()
    limit = max(1, min(int(limit or 10), 100))

    if act == "add":
        if not (title or content):
            return {"ok": False, "output": "add 需要 title 或 content"}
        new_id = "kb_" + uuid.uuid4().hex[:10]
        conn.execute("INSERT INTO kb (id,title,content,tags,created_at) VALUES (?,?,?,?,?)",
                     (new_id, (title or "").strip(), (content or "").strip(),
                      (tags or "").strip(), time.time()))
        conn.commit()
        return {"output": f"已写入 [{new_id}] {title or '(无题)'}。当前条目: " +
                 str(conn.execute("SELECT COUNT(*) FROM kb").fetchone()[0])}

    if act == "list":
        rows = conn.execute("SELECT id,title,tags FROM kb ORDER BY created_at DESC LIMIT ?",
                            (limit,)).fetchall()
        if not rows:
            return {"output": "（知识库为空）"}
        lines = [f"- [{r[0]}] {r[1] or '(无题)'}" + (f"  #{' '.join(t for t in r[2].split(',') if t)}" if r[2] else "")
                 for r in rows]
        return {"output": "\n".join(lines)}

    if act == "delete":
        if not id:
            return {"ok": False, "output": "delete 需要 id"}
        cur = conn.execute("DELETE FROM kb WHERE id=?", (id.strip(),))
        conn.commit()
        return {"output": f"已删除 {cur.rowcount} 条"}

    if act == "search":
        if not query:
            return {"ok": False, "output": "search 需要 query"}
        toks = _tokens(query)
        rows = conn.execute("SELECT id,title,content,tags FROM kb").fetchall()
        scored = []
        for rid, t, c, tg in rows:
            hay = f"{t} {c} {tg}".lower()
            score = sum(1 for tok in toks if tok in hay)
            exact = sum(1 for tok in toks if tok in (t or "").lower())
            if score:
                scored.append((score * 2 + exact * 3, rid, t, c, tg))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            return {"output": f"知识库中未找到匹配 `{query}` 的条目"}
        lines = [f"检索 `{query}`：{len(scored)} 条相关"]
        for s, rid, t, c, tg in scored[:limit]:
            lines.append(f"- [{rid}] {t or '(无题)'}" + (f"  #{tg}" if tg else ""))
            if c:
                lines.append(f"   {c[:200]}")
        return {"output": "\n".join(lines)}

    conn.close()
    return {"ok": False, "output": f"未知 action: {action}（可选 add/search/list/delete）"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
