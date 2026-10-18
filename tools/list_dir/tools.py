"""列出目录内容 / 查看工作区结构。"""

from __future__ import annotations

from pathlib import Path

from common import relative, resolve_path, workspace_dir

NAME = "list_dir"
DESCRIPTION = "列出工作区中某个目录下的文件与子目录，可按扩展名过滤、可递归"
PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "目录路径，默认工作区根目录，用 . 表示"},
        "recursive": {"type": "boolean", "description": "是否递归列出子目录，默认 false"},
        "extension": {"type": "string", "description": "按扩展名过滤，例如 .py；省略则不过滤"},
        "ignore_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要忽略的通配符模式（匹配路径任意一级），例如 [\"*.log\", \"temp*\"]",
        },
        "max_entries": {"type": "integer", "description": "最多返回条数，默认 300"},
    },
    "required": [],
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "dist", "build"}


def _ignored(rel: str, globs: list[str]) -> bool:
    import fnmatch

    parts = Path(rel).parts
    for g in globs:
        if fnmatch.fnmatch(rel, g) or any(fnmatch.fnmatch(part, g) for part in parts):
            return True
    return False


def run(path: str = ".", recursive: bool = False, extension: str | None = None,
        ignore_globs: list[str] | None = None, max_entries: int = 300) -> dict:
    target: Path = resolve_path(path) if path not in ("", None) else workspace_dir().resolve()
    if not target.exists():
        return {"ok": False, "output": f"目录不存在: {relative(target)}"}
    if not target.is_dir():
        return {"ok": False, "output": f"不是目录: {relative(target)}（读取文件请用 read_file）"}

    root = workspace_dir().resolve()
    globs = [str(g) for g in (ignore_globs or []) if str(g).strip()]
    pattern = f"**/*" if recursive else "*"
    entries = []
    for item in sorted(target.glob(pattern)):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        rel = relative(item)
        if globs and _ignored(rel, globs):
            continue
        if item.is_dir():
            entries.append((item, "dir", 0))
        else:
            try:
                size = item.stat().st_size
            except OSError:
                continue
            entries.append((item, "file", size))

    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        entries = [e for e in entries if e[1] == "dir" or e[0].suffix.lower() == ext.lower()]

    lines = [f"[{'递归' if recursive else '当前目录'}] {relative(target) or '.'}"]
    base_depth = len(Path(relative(target) or '.').parts)
    for item, kind, size in entries[:max_entries]:
        rel = relative(item)
        depth = max(0, len(Path(rel).parts) - base_depth)
        indent = "  " * depth
        lines.append(f"{indent}{item.name}{'/' if kind == 'dir' else f'  ({size} B)'}")
    if len(entries) > max_entries:
        lines.append(f"... 共 {len(entries)} 项，仅显示前 {max_entries} 项")
    lines.append(f"\n工作区根目录: {root}")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
