"""写入（新建或整体覆盖）工作区内的文件。"""

from __future__ import annotations

from pathlib import Path

from common import read_text, record_change, relative, resolve_path

NAME = "write_file"
DESCRIPTION = "创建新文件或整体覆盖已有文件，变更会记录到右侧文件变更面板"
PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作区的目标文件路径"},
        "content": {"type": "string", "description": "文件的完整新内容"},
        "overwrite": {"type": "boolean", "description": "文件已存在时是否覆盖，默认 false"},
    },
    "required": ["path", "content"],
}


def run(path: str, content: str, overwrite: bool = False) -> dict:
    target: Path = resolve_path(path)
    existed = target.exists()
    if existed and not overwrite:
        return {"ok": False, "output": f"文件已存在: {relative(target)}。请先 read_file 读取，再使用 edit_file 修改，或显式设置 overwrite=true。"}

    before = read_text(target) if existed else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    text = content if content.endswith("\n") or not content else content + "\n"
    target.write_text(text, encoding="utf-8")

    record_change(target, "modify" if existed else "create", before=before, after=text)
    action = "已覆盖写入" if existed else "已新建"
    lines = text.count("\n") + (1 if text else 0)
    return {"output": f"{action}文件 {relative(target)}（{lines} 行, {len(text)} 字符）"}


__all__ = ["DESCRIPTION", "NAME", "PARAMETERS", "run"]
