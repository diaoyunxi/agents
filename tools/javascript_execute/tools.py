"""执行 JavaScript / Node 代码（本机需安装 node）。"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from common import record_change, workspace_dir

NAME = "javascript_execute"
DANGEROUS = True
DESCRIPTION = "执行一段 JavaScript / Node 代码（本机需 node），回显 stdout/stderr/退出码"
PARAMETERS = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "要执行的 JS 源码（CommonJS）"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 300"},
        "stdin": {"type": "string", "description": "可选：写入标准输入"},
    },
    "required": ["code"],
}

REQUIRES = ["cli:node"]  # 本机未装 node 时自动停用


def run(code: str, timeout: int = 30, stdin: str = "") -> dict:
    if not code or not code.strip():
        return {"ok": False, "output": "code 不能为空"}
    timeout = max(1, min(int(timeout or 30), 300))

    ws = workspace_dir().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    script = ws / f"_tmp_js_{uuid.uuid4().hex[:10]}.js"
    script.write_text(code, encoding="utf-8")
    record_change(script, "create")

    import shutil
    node = shutil.which("node")
    if node is None:
        script.unlink(missing_ok=True)
        return {"ok": False, "output": "未找到 node，无法执行 JS。请安装 Node.js 或改用 python_execute。"}
    try:
        proc = subprocess.run([node, str(script)], input=(stdin or "").encode("utf-8"),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, cwd=str(ws))
    except subprocess.TimeoutExpired:
        script.unlink(missing_ok=True)
        return {"ok": False, "output": f"执行超时（>{timeout}s）已终止"}
    finally:
        script.unlink(missing_ok=True)

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"exit_code: {proc.returncode}"]
    if stdout:
        parts.append("--- stdout ---\n" + stdout[:12000])
    if stderr:
        parts.append("--- stderr ---\n" + stderr[:4000])
    return {"ok": proc.returncode == 0, "output": "\n".join(parts)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES", "DANGEROUS"]
