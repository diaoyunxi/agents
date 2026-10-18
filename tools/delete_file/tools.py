"""删除工作区内的文件。"""

from __future__ import annotations

from pathlib import Path

from common import SandboxError, read_text, record_change, relative, resolve_path, workspace_dir

NAME = "delete_file"
DESCRIPTION = "删除工作区中的一个文件（不可恢复，删除前请确认；目录请用 execute_command 处理）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string", "description": "相对工作区的目标文件路径，必须已存在"},
    },
    "required": ["filePath"],
}


def run(filePath: str) -> dict:
    try:
        target: Path = resolve_path(filePath, must_exist=True)
    except SandboxError as exc:
        return {"ok": False, "output": str(exc)}
    rel = relative(target)

    if target == workspace_dir().resolve():
        return {"ok": False, "output": "不能删除工作区根目录"}
    if target.is_dir():
        return {"ok": False, "output": f"{rel} 是目录，本工具只删文件；删除目录请谨慎使用 execute_command"}

    before = ""
    try:
        before = read_text(target, limit=20000)
    except OSError:
        pass
    try:
        target.unlink()
    except OSError as exc:
        return {"ok": False, "output": f"删除失败: {rel}（{exc}）"}

    record_change(target, "delete", before=before, after="")
    return {"output": f"已删除文件 {rel}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
