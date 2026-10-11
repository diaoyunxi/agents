"""读取工作区内文件的内容。"""

from __future__ import annotations

from pathlib import Path

from common import read_text, relative, resolve_path

NAME = "read_file"
DESCRIPTION = "读取工作区中某个文件（或目录列表）的文本内容"
PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作区的文件路径，例如 src/app.py"},
        "start_line": {"type": "integer", "description": "起始行号（从 1 开始），可选"},
        "end_line": {"type": "integer", "description": "结束行号（含），可选"},
        "max_chars": {"type": "integer", "description": "最多返回的字符数，默认 20000"},
    },
    "required": ["path"],
}


def run(path: str, start_line: int | None = None, end_line: int | None = None, max_chars: int = 20000) -> dict:
    target: Path = resolve_path(path, must_exist=True)
    if target.is_dir():
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"[目录] {relative(target)}"] + [f"  {e.name}{'/' if e.is_dir() else ''}" for e in entries[:500]]
        return {"output": "\n".join(lines)}

    text = read_text(target, limit=max_chars)
    total_lines = text.count("\n") + 1
    numbered_all = text.splitlines()
    begin = max(1, int(start_line or 1))
    finish = min(total_lines, int(end_line or total_lines))
    slice_ = numbered_all[begin - 1 : finish]
    body = "\n".join(f"{begin + i:>6} | {line}" for i, line in enumerate(slice_))
    header = f"文件: {relative(target)} | 总行数: {total_lines} | 显示范围: {begin}-{finish}"
    return {"output": f"{header}\n{body}"}


__all__ = ["DESCRIPTION", "NAME", "PARAMETERS", "run"]
