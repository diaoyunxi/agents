"""按通配符模式递归搜索文件名。"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from common import relative, resolve_path, workspace_dir

NAME = "search_file"
DESCRIPTION = "按通配符模式递归搜索文件/目录名（如 *.py、test_*.js），返回匹配路径列表"
PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "通配符模式，例如 *.py、test_*.js、*config*"},
        "path": {"type": "string", "description": "限定搜索的目录，默认整个工作区，用 . 表示"},
        "recursive": {"type": "boolean", "description": "是否递归子目录，默认 true"},
        "ignore_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要忽略的通配符模式（匹配路径任意一级），例如 [\"node_modules\", \"*.min.js\"]",
        },
        "max_results": {"type": "integer", "description": "最多返回条数，默认 200"},
    },
    "required": ["pattern"],
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "dist", "build"}


def _ignored(rel: str, globs: list[str]) -> bool:
    parts = Path(rel).parts
    for g in globs:
        if fnmatch.fnmatch(rel, g) or any(fnmatch.fnmatch(part, g) for part in parts):
            return True
    return False


def run(pattern: str, path: str = ".", recursive: bool = True,
        ignore_globs: list[str] | None = None, max_results: int = 200) -> dict:
    pattern = (pattern or "").strip()
    if not pattern:
        return {"ok": False, "output": "pattern 不能为空，例如 *.py"}

    base: Path = resolve_path(path) if path not in ("", None) else workspace_dir().resolve()
    if not base.exists():
        return {"ok": False, "output": f"目录不存在: {relative(base)}"}
    if not base.is_dir():
        return {"ok": False, "output": f"不是目录: {relative(base)}"}

    globs = [str(g) for g in (ignore_globs or []) if str(g).strip()]
    hits: list[str] = []
    walker = base.rglob("*") if recursive else base.glob("*")
    for item in walker:
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        rel = relative(item)
        if globs and _ignored(rel, globs):
            continue
        if fnmatch.fnmatch(item.name, pattern):
            hits.append(f"  {rel}{'/' if item.is_dir() else ''}")
            if len(hits) >= max_results:
                break

    header = f"模式: {pattern} | 范围: {relative(base) or '.'} | 递归: {recursive}"
    if not hits:
        return {"output": f"{header}\n未找到匹配项"}
    body = "\n".join(hits)
    note = f"\n... 结果已达上限 {max_results}，请缩小范围或细化模式" if len(hits) >= max_results else ""
    return {"output": f"{header}\n{body}{note}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
