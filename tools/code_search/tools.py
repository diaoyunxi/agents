"""代码搜索：在工作区内搜代码（复用 search_content），或给出 GitHub 公开代码检索入口。"""

from __future__ import annotations

import urllib.parse

NAME = "code_search"
DESCRIPTION = "按关键词搜代码：scope=local 搜工作区内代码（复用 search_content）；scope=github 给出公开代码检索链接"
PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "要搜的代码/函数/模式，如 `def __init__` 或 `async with httpx`"},
        "scope": {"type": "string", "description": "local=工作区（默认）；github=公开代码", "enum": ["local", "github"]},
        "language": {"type": "string", "description": "限定语言/扩展名，如 python / rust / go"},
        "glob": {"type": "string", "description": "local 用：文件名通配，如 `*.ts`；可与 language 二选一"},
        "max_results": {"type": "integer", "description": "最多返回条数，默认 10"},
    },
    "required": ["query"],
}


def _local(query: str, language: str, glob: str, max_results: int) -> str:
    from tools import loader as tool_loader
    item = tool_loader.get_tool("search_content")
    if item is None:
        return "（工作区搜索不可用：search_content 未加载）"
    g = (glob or "").strip() or (f"*.{language}" if (language or "").strip() else None)
    args = {"pattern": query, "outputMode": "content", "maxResults": max_results}
    if g:
        args["glob"] = g
    outcome = item["run"](**args)
    return str(outcome.get("output", "")) or "（工作区内未找到匹配）"


def _github(query: str, language: str) -> str:
    q = query + (f" language:{language}" if language else "")
    url = "https://github.com/search?" + urllib.parse.urlencode(
        {"q": q, "type": "code"})
    lines = [f"GitHub 代码检索: `{query}`" + (f"（语言: {language}）" if language else "")]
    lines.append("免密钥入口（浏览器打开）: " + url)
    lines.append("提示: GitHub 代码搜索 API 需要 Personal Access Token；自动化场景请用 http_request 带 token 调用 "
                 "https://api.github.com/search/code。")
    return "\n".join(lines)


def run(query: str, scope: str = "local", language: str = "", glob: str = "", max_results: int = 10) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "output": "query 不能为空"}
    max_results = max(1, min(int(max_results or 10), 50))
    if scope == "github":
        return {"output": _github(query, language)}
    return {"output": _local(query, language, glob, max_results)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
