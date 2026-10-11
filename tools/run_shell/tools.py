"""在工作区中执行 shell 命令。"""

from __future__ import annotations

import os
import shlex
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

BLOCKED = ["rm -rf /", "rm -rf ~", "format ", "shutdown", "mkfs", "del /f /s /q c:", ":(){:|:&};:"]


def run(command: str, timeout: int = 120, cwd: str | None = None) -> dict:
    if not command.strip():
        return {"ok": False, "output": "命令为空"}
    low = command.lower()
    for bad in BLOCKED:
        if bad in low:
            return {"ok": False, "output": f"命令被安全策略拒绝（包含危险片段: {bad.strip()}）"}

    root = workspace_dir().resolve()
    work_dir = (root / cwd).resolve() if cwd else root
    try:
        work_dir.relative_to(root)
    except ValueError as exc:
        raise SandboxError(f"工作目录 {work_dir} 超出工作区") from exc

    timeout = max(5, min(int(timeout or 120), 600))

    # 使用 shlex.split() 解析命令参数，shell=False 防止命令注入 (CWE-78)
    try:
        args = shlex.split(command)
    except ValueError as exc:
        return {"ok": False, "output": f"命令解析失败: {exc}"}
    if not args:
        return {"ok": False, "output": "命令为空"}

    # 安全的环境变量白名单，避免泄露敏感信息
    _SAFE_ENV_KEYS = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL", "PWD", "TMPDIR"}
    safe_env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
    safe_env["TERM"] = "dumb"

    try:
        proc = subprocess.run(
            args,
            shell=False,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=safe_env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"命令超时（>{timeout}s）被终止"}
    except FileNotFoundError:
        return {"ok": False, "output": f"命令未找到: {args[0]}"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"$ {command}", f"cwd: {work_dir}", f"exit_code: {proc.returncode}"]
    if stdout:
        parts.append("--- stdout ---\n" + stdout[:20000])
    if stderr:
        parts.append("--- stderr ---\n" + stderr[:8000])
    return {"ok": proc.returncode == 0, "output": "\n".join(parts)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
