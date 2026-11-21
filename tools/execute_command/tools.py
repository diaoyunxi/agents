"""在工作区中执行 Shell / PowerShell 命令。"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

from common import SandboxError, workspace_dir

NAME = "execute_command"
DANGEROUS = True
DESCRIPTION = "在工作区目录中执行一条 Shell/PowerShell 命令并返回输出（用于 git、pip、测试、构建等）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "要执行的命令行字符串"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 120，最大 600"},
        "cwd": {"type": "string", "description": "工作目录（相对工作区），默认为工作区根目录"},
    },
    "required": ["command"],
}

BLOCKED = ["rm -rf /", "rm -rf ~", "format ", "shutdown", "mkfs", "del /f /s /q c:", ":(){:|:&};:"]

# 正则黑名单：堵住子串匹配的常见绕过（多余空格、绝对路径前缀、fork bomb 变体）(CWE-184)
_BLOCKED_PATTERNS = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+[/~]"), "rm -rf / 或 rm -rf ~"),
    (re.compile(r"\bmkfs\b"), "mkfs (格式化命令)"),
    (re.compile(r"\b(shutdown|halt|reboot|poweroff)\b"), "系统电源控制命令"),
    (re.compile(r"\bdd\s+if="), "dd if= (裸盘写入)"),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
    (re.compile(r"\bformat\s+[a-zA-Z]:"), "format (Windows 格式化)"),
    (re.compile(r"\bdel\s+/[fs]"), "del /f /s (Windows 批量删除)"),
]

# 需要 shell 解析的语法结构；只有出现这些时才退回 shell=True
_SHELL_SYNTAX = re.compile(r"[|;&<>]|\$\(|`")


def _blocked_reason(command: str) -> str | None:
    """返回命中的危险模式说明，未命中返回 None。"""
    low = command.lower()
    for bad in BLOCKED:
        if bad in low:
            return bad.strip()
    for pattern, desc in _BLOCKED_PATTERNS:
        if pattern.search(low):
            return desc
    return None


def _needs_shell(command: str) -> bool:
    """命令是否包含管道/重定向/命令替换等必须由 shell 解析的结构。"""
    in_single = in_double = False
    for ch in command:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and _SHELL_SYNTAX.search(ch):
            return True
    return False


def run(command: str, timeout: int = 120, cwd: str | None = None) -> dict:
    if not command or not command.strip():
        return {"ok": False, "output": "命令为空"}
    hit = _blocked_reason(command)
    if hit:
        return {"ok": False, "output": f"命令被安全策略拒绝（包含危险片段: {hit}）"}

    root = workspace_dir().resolve()
    work_dir = (root / cwd).resolve() if cwd else root
    try:
        work_dir.relative_to(root)
    except ValueError as exc:
        raise SandboxError(f"工作目录 {work_dir} 超出工作区") from exc
    if not work_dir.is_dir():
        return {"ok": False, "output": f"工作目录不存在: {work_dir}"}

    timeout = max(5, min(int(timeout or 120), 600))
    # 默认用 shlex.split + shell=False，消除命令注入面 (CWE-78)；
    # 仅当命令确实包含管道/重定向/命令替换时，才退回 shell=True（此时防护依赖上面的黑名单）。
    use_shell = _needs_shell(command)
    if use_shell:
        args = command
    else:
        try:
            args = shlex.split(command)
        except ValueError as exc:
            return {"ok": False, "output": f"命令解析失败: {exc}"}
        if not args:
            return {"ok": False, "output": "命令为空"}

    try:
        proc = subprocess.run(
            args,
            shell=use_shell,  # noqa: S602 — 仅在需要 shell 语法时为 True
            check=False,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"命令超时（>{timeout}s）被终止"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"$ {command}", f"cwd: {work_dir}", f"exit_code: {proc.returncode}"]
    if stdout:
        parts.append("--- stdout ---\n" + stdout[:20000])
    if stderr:
        parts.append("--- stderr ---\n" + stderr[:8000])
    return {"ok": proc.returncode == 0, "output": "\n".join(parts)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
