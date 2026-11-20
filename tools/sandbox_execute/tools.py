"""受限沙箱执行：在隔离临时目录里跑命令/脚本，默认断网、限超时、限定工作区。"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from common import workspace_dir

NAME = "sandbox_execute"
DANGEROUS = True
DESCRIPTION = "在隔离沙箱中执行命令（默认断网、新临时目录、限超时），比 execute_command 更保守，适合不受信的脚本"
PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "要执行的命令行（在沙箱内）"},
        "allow_network": {"type": "boolean", "description": "是否允许网络，默认 false（通过环境变量断网）"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 300"},
    },
    "required": ["command"],
}


def run(command: str, allow_network: bool = False, timeout: int = 30) -> dict:
    if not (command or "").strip():
        return {"ok": False, "output": "command 不能为空"}
    timeout = max(1, min(int(timeout or 30), 300))

    ws = workspace_dir().resolve()
    sandbox = Path(tempfile.mkdtemp(prefix="agents_sb_"))
    env = dict(os.environ)
    if not allow_network:
        # 尽力断网：把代理指向不可达地址，多数客户端/库会失败
        env.update({
            "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
            "no_proxy": "", "NO_PROXY": "",
        })

    try:
        proc = subprocess.run(command, shell=True, cwd=str(sandbox),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"沙箱执行超时（>{timeout}s）已终止（网络{'允许' if allow_network else '已断'}）"}
    finally:
        # 清理临时沙箱
        for child in sandbox.rglob("*"):
            if child.is_file():
                child.unlink(missing_ok=True)
        sandbox.rmdir()

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"沙箱执行（网络: {'允许' if allow_network else '已断'} | 目录: 隔离临时目录）",
             f"$ {command}", f"exit_code: {proc.returncode}"]
    if stdout:
        parts.append("--- stdout ---\n" + stdout[:8000])
    if stderr:
        parts.append("--- stderr ---\n" + stderr[:3000])
    note = "" if allow_network else "\n（提示: 默认已断网；需要联网请设 allow_network=true 或改用 execute_command）"
    return {"ok": proc.returncode == 0, "output": "\n".join(parts) + note}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "DANGEROUS"]
