"""Git / GitHub 仓库操作：在工作区内执行 git 子命令（只读为主，写需确认）。"""

from __future__ import annotations

import subprocess

from common import SandboxError, workspace_dir

NAME = "git_ops"
DANGEROUS = True
DESCRIPTION = "执行 git 命令（status/log/diff/blame/commit/branch/pull/push 等）并返回输出；写操作请谨慎"
PARAMETERS = {
    "type": "object",
    "properties": {
        "git_args": {"type": "string", "description": "git 子命令及参数，如 `status -s`、`log --oneline -10`、`diff --staged`"},
        "cwd": {"type": "string", "description": "仓库目录（相对工作区），默认工作区根"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 120"},
    },
    "required": ["git_args"],
}

REQUIRES = ["cli:git"]  # 本机未装 git 时自动停用

# 只读/无副作用子命令：可直接执行
SAFE_PREFIXES = ("status", "log", "diff", "show", "branch", "remote", "tag",
                 "rev-parse", "ls-files", "shortlog", "describe", "blame")


def run(git_args: str, cwd: str | None = None, timeout: int = 120) -> dict:
    args = (git_args or "").strip()
    if not args:
        return {"ok": False, "output": "git_args 不能为空"}

    try:
        root = workspace_dir().resolve()
        work_dir = (root / cwd).resolve() if cwd else root
        work_dir.relative_to(root)
    except SandboxError as exc:
        return {"ok": False, "output": str(exc)}

    timeout = max(5, min(int(timeout or 120), 600))
    cmd = ["git"] + args.split()
    try:
        proc = subprocess.run(cmd, cwd=str(work_dir), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "output": "未找到 git 可执行文件"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"git 命令超时（>{timeout}s）"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    head = args.split()[0] if args.split() else ""
    warning = ""
    if head not in SAFE_PREFIXES:
        warning = "\n（注意：这是写操作，已实际执行，请确认影响）"

    parts = [f"$ git {args}", f"cwd: {work_dir}", f"exit_code: {proc.returncode}"]
    if stdout:
        parts.append("--- stdout ---\n" + stdout[:12000])
    if stderr:
        parts.append("--- stderr ---\n" + stderr[:4000])
    return {"ok": proc.returncode == 0, "output": "\n".join(parts) + warning}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES", "DANGEROUS"]
