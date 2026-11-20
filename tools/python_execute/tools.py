"""安全执行 Python 代码：写入临时脚本到工作区，受限执行并回显 stdout/stderr。"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from common import SandboxError, record_change, relative, workspace_dir

NAME = "python_execute"
DANGEROUS = True
DESCRIPTION = "执行一段 Python 代码（受限：默认 30s 超时），返回 stdout/stderr/退出码，适合数据处理与脚本验证"
PARAMETERS = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "要执行的 Python 源码"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 30，最大 300"},
        "stdin": {"type": "string", "description": "可选：写入标准输入的内容"},
    },
    "required": ["code"],
}

# 本机必然有 Python（本运行时即 Python）；若环境异常可声明 REQUIRES=["cli:python3"]
# 这里始终启用，执行期若找不到解释器会明确报错。


def run(code: str, timeout: int = 30, stdin: str = "") -> dict:
    if not code or not code.strip():
        return {"ok": False, "output": "code 不能为空"}
    timeout = max(1, min(int(timeout or 30), 300))

    ws = workspace_dir().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    script = ws / f"_tmp_pyexec_{uuid.uuid4().hex[:10]}.py"
    script.write_text(code, encoding="utf-8")
    record_change(script, "create")

    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=(stdin or "").encode("utf-8"),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(ws),
        )
    except subprocess.TimeoutExpired:
        script.unlink(missing_ok=True)
        return {"ok": False, "output": f"执行超时（>{timeout}s）已终止\n（脚本已清理: {script.name}）"}
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


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "DANGEROUS"]
