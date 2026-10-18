"""写入（新建或整体覆盖）工作区内的文件。"""

from __future__ import annotations

from pathlib import Path

from common import SandboxError, read_text, record_change, relative, resolve_path

NAME = "write_to_file"
DESCRIPTION = "创建新文件或整体覆盖已有文件，父目录不存在会自动创建，变更记录到文件变更面板"
PARAMETERS = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string", "description": "相对工作区的目标文件路径"},
        "content": {"type": "string", "description": "文件的完整新内容（整体覆盖）"},
    },
    "required": ["filePath", "content"],
}


def run(filePath: str, content: str) -> dict:
    if content is None:
        return {"ok": False, "output": "content 不能为空"}
    try:
        target: Path = resolve_path(filePath)
    except SandboxError as exc:
        return {"ok": False, "output": str(exc)}
    if target.is_dir():
        return {"ok": False, "output": f"{relative(target)} 是目录，无法写入"}
    existed = target.exists()

    before = read_text(target) if existed else ""
    # 覆盖已存在的 CRLF 文件时保持其换行风格，避免整文件行尾漂移
    text = content if content.endswith("\n") or not content else content + "\n"
    if existed and "\r\n" in before:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    except OSError as exc:
        return {"ok": False, "output": f"写入失败: {relative(target)}（{exc}）"}

    record_change(target, "modify" if existed else "create", before=before, after=text)
    action = "已覆盖写入" if existed else "已新建"
    lines = text.count("\n") + (1 if text else 0)
    return {"output": f"{action}文件 {relative(target)}（{lines} 行, {len(text)} 字符）"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
