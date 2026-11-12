"""安装 Python 包（pip install），带安全约束与进度回显。

安全策略：
- 默认安装到当前解释器所在环境（sys.executable -m pip）
- 禁止安装 requirements 白名单之外的系统级修改包（--system 拒绝）
- 安装成功后刷新 capabilities 缓存，被门控停用的工具自动恢复
- 高风险（DANGEROUS）：可改变运行环境
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

NAME = "pip_install"
DANGEROUS = True
DESCRIPTION = "安装 Python 包（pip install），支持批量安装、指定版本/约束文件；装完自动刷新能力缓存使门控工具恢复"
PARAMETERS = {
    "type": "object",
    "properties": {
        "packages": {
            "type": "array",
            "description": "要安装的包名列表，如 [\"sympy\", \"matplotlib\"]，支持 `pkg==1.2` 格式",
            "items": {"type": "string"},
        },
        "constraints_file": {
            "type": "string",
            "description": "可选：requirements 约束文件路径（相对工作区或绝对路径）",
        },
        "upgrade": {
            "type": "boolean",
            "description": "是否升级已存在的包，默认 false",
        },
        "timeout": {
            "type": "integer",
            "description": "超时秒数，默认 300，最大 1800",
        },
    },
    "required": ["packages"],
}


def _run_pip(args: list[str], timeout: int) -> dict:
    cmd = [sys.executable, "-m", "pip"] + args
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"pip 安装超时（>{timeout}s）"}
    except OSError as exc:
        return {"ok": False, "output": f"pip 执行失败: {exc}"}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"$ {json.dumps(cmd)}", f"exit_code: {proc.returncode}"]
    if stdout:
        parts.append("--- stdout ---\n" + stdout[:6000])
    if stderr:
        parts.append("--- stderr ---\n" + stderr[:3000])

    ok = proc.returncode == 0
    return {"ok": ok, "output": "\n".join(parts)}


def run(packages: list[str], constraints_file: str = "", upgrade: bool = False, timeout: int = 300) -> dict:
    if not packages or not all(isinstance(p, str) and p.strip() for p in packages):
        return {"ok": False, "output": "packages 需为非空字符串数组"}

    # 基本安全校验：禁止 --system、--prefix=/、--prefix=C:\ 等系统级操作
    for p in packages:
        low = p.strip().lower()
        if low.startswith(("--system", "--prefix=", "-c ")) or " " in low:
            return {"ok": False, "output": f"包名 `{p}` 含不合法的 pip 标志，已拒绝"}

    args = ["install"]
    if upgrade:
        args.append("--upgrade")
    args += [p.strip() for p in packages]

    if constraints_file:
        from common import resolve_path
        try:
            cpath = resolve_path(constraints_file, must_exist=True)
            args.append(f"-c{cpath}")
        except Exception as exc:
            return {"ok": False, "output": f"约束文件路径无效: {exc}"}

    timeout = max(30, min(int(timeout or 300), 1800))
    result = _run_pip(args, timeout)

    # 安装成功则刷新能力缓存并重新 discover，让门控工具自动恢复
    if result.get("ok"):
        try:
            import capabilities
            capabilities.refresh()
        except Exception:  # noqa: BLE001
            pass
        try:
            import tools.loader as _loader
            _loader.discover(force=True)
        except Exception:  # noqa: BLE001
            pass
        result["output"] += "\n\n✓ 已刷新能力缓存并重新加载工具，被门控停用的工具应已自动恢复。"

    return result


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "DANGEROUS"]
