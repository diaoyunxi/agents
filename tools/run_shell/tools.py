"""在工作区中执行 shell 命令。"""

from __future__ import annotations

import shlex
import subprocess

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

# 危险的 shell 元字符，用于检测潜在的注入攻击
SHELL_META = set("|;&$`(){}[]<>!#~")


def _looks_like_shell_pipeline(command: str) -> bool:
    """检测命令是否包含管道/重定向等需要 shell 解析的结构。"""
    in_single = False
    in_double = False
    for ch in command:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and ch in "|&><":
            return True
    return False


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

    # 安全修复：优先使用 shell=False + shlex.split 防止命令注入 (CWE-78, S602)
    # 仅当命令包含管道/重定向等 shell 结构时才回退到 shell=True
    use_shell = _looks_like_shell_pipeline(command)
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
            shell=use_shell,  # noqa: S602 — 仅在检测到管道/重定向时使用
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


__all__ = ["DESCRIPTION", "NAME", "PARAMETERS", "run"]
