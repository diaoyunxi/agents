"""在工作区中执行 shell 命令。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from common import SandboxError, workspace_dir

NAME = "run_shell"
DANGEROUS = True
DESCRIPTION = "在工作区目录中执行一条 shell 命令并返回输出（用于 git、pip、测试等）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "要执行的命令行字符串"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 120，最大 600"},
        "cwd": {"type": "string", "description": "工作目录（相对工作区），默认为工作区根目录"},
    },
    "required": ["command"],
}

BLOCKED = [
    "rm -rf /", "rm -rf ~", "format ", "shutdown", "mkfs",
    "del /f /s /q c:", ":(){:|:&};:",
]

# 正则黑名单：防止简单字符串匹配的绕过（CWE-184）
# - rm -rf / → rm -rf //, rm -rf /., rm  -rf  /  (多余空格)
# - shutdown → /sbin/shutdown, sudo shutdown
# - mkfs → mkfs.ext4, mkfs -t ext4
# - fork bomb 变体
_BLOCKED_PATTERNS = [
    (re.compile(r'\brm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+[/~]'), "rm -rf / 或 rm -rf ~"),
    (re.compile(r'\bmkfs\b'), "mkfs (格式化命令)"),
    (re.compile(r'\bshutdown\b'), "shutdown (关机命令)"),
    (re.compile(r'\bhalt\b|\breboot\b|\bpoweroff\b'), "系统控制命令"),
    (re.compile(r'\bdd\s+if='), "dd if= (磁盘写入)"),
    (re.compile(r':\(\)\s*\{'), "fork bomb"),
    (re.compile(r'\bformat\s+[a-zA-Z]:'), "format (Windows格式化)"),
    (re.compile(r'\bdel\s+/[fs]'), "del /f /s (Windows批量删除)"),
]


def _check_blocked(command: str) -> str | None:
    """
    检查命令是否被黑名单拦截。
    返回 None 表示通过，否则返回拒绝原因。
    """
    low = command.lower().strip()

    # 精确子串匹配（向后兼容）
    for bad in BLOCKED:
        if bad in low:
            return f"包含危险片段: {bad.strip()}"

    # 正则匹配（防绕过：多余空格、路径变体、前缀路径等）
    for pattern, desc in _BLOCKED_PATTERNS:
        if pattern.search(low):
            return f"匹配危险模式: {desc}"

    return None


def run(command: str, timeout: int = 120, cwd: str | None = None) -> dict:
    if not command.strip():
        return {"ok": False, "output": "命令为空"}
    blocked_reason = _check_blocked(command)
    if blocked_reason:
        return {"ok": False, "output": f"命令被安全策略拒绝（{blocked_reason}）"}

    root = workspace_dir().resolve()
    work_dir = (root / cwd).resolve() if cwd else root
    try:
        work_dir.relative_to(root)
    except ValueError as exc:
        raise SandboxError(f"工作目录 {work_dir} 超出工作区") from exc

    timeout = max(5, min(int(timeout or 120), 600))
    try:
        proc = subprocess.run(
            command,
            shell=True,
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
