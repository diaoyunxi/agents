"""在工作区内按内容 / 文件名搜索。"""

from __future__ import annotations

import re
from pathlib import Path

from common import read_text, relative, resolve_path, workspace_dir

NAME = "search_files"
DESCRIPTION = "在工作区内按文件名或文件内容进行搜索，返回匹配的文件与行"
PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "要搜索的关键词或正则表达式"},
        "path": {"type": "string", "description": "限定搜索的子目录，默认整个工作区"},
        "glob": {"type": "string", "description": "文件名过滤，例如 *.py，默认搜索常见代码文件"},
        "regex": {"type": "boolean", "description": "是否按正则表达式解析 pattern，默认 false"},
        "ignore_case": {"type": "boolean", "description": "是否忽略大小写，默认 true"},
        "max_results": {"type": "integer", "description": "最多返回结果条数，默认 100"},
    },
    "required": ["pattern"],
}

DEFAULT_GLOBS = ("*.py", "*.md", "*.txt", "*.json", "*.js", "*.ts", "*.tsx", "*.jsx", "*.html", "*.css", "*.yml", "*.yaml", "*.toml")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "dist", "build"}


def run(pattern: str, path: str = ".", glob: str | None = None, regex: bool = False,
        ignore_case: bool = True, max_results: int = 100) -> dict:
    base: Path = resolve_path(path) if path not in ("", None) else workspace_dir().resolve()
    if not base.exists():
        return {"ok": False, "output": f"目录不存在: {relative(base)}"}

    flags = re.IGNORECASE if ignore_case else 0
    try:
        matcher = re.compile(pattern, flags) if regex else None
    except re.error as exc:
        return {"ok": False, "output": f"正则表达式无效: {exc}"}
    needle = pattern.lower() if ignore_case else pattern

    globs = (glob,) if glob else DEFAULT_GLOBS
    hits: list[str] = []
    name_hits: list[str] = []

    for g in globs:
        for item in sorted(base.glob(f"**/{g}")):
            if not item.is_file() or any(part in SKIP_DIRS for part in item.parts):
                continue
            rel = relative(item)
            if matcher is None and needle in item.name.lower():
                name_hits.append(f"  {rel}")
            if matcher is None and not ignore_case and needle in item.name:
                name_hits.append(f"  {rel}")
            try:
                text = read_text(item)
            except Exception:  # noqa: BLE001
                continue
            for idx, line in enumerate(text.splitlines(), 1):
                matched = matcher.search(line) if matcher else (needle in line.lower())
                if matched:
                    hits.append(f"  {rel}:{idx}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        break
            if len(hits) >= max_results:
                break
        if len(hits) >= max_results:
            break

    parts = [f"搜索模式: {pattern} | 范围: {relative(base) or '.'} | 忽略大小写: {ignore_case}"]
    if name_hits:
        parts.append("文件名匹配:\n" + "\n".join(name_hits[:20]))
    parts.append("内容匹配:" + ("\n" + "\n".join(hits) if hits else " 无"))
    if len(hits) >= max_results:
        parts.append(f"... 结果已达上限 {max_results}，请缩小范围或调整关键词")
    return {"output": "\n".join(parts)}


__all__ = ["DESCRIPTION", "NAME", "PARAMETERS", "run"]
