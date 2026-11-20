"""Docker 容器/镜像/Compose 管理（本机需 docker CLI，未装则自动停用）。"""

from __future__ import annotations

import json
import subprocess

from common import workspace_dir

NAME = "docker_manage"
DANGEROUS = True
DESCRIPTION = "管理 Docker：list/ps/logs/inspect/build/run/stop/remove/compose up（本机需 docker）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "ps=运行中容器；images=镜像；logs=某容器日志；inspect=某对象详情；build=构建；run=运行；stop=停止；remove=删除；compose=跑 compose 子命令",
            "enum": ["ps", "images", "logs", "inspect", "build", "run", "stop", "remove", "compose"],
        },
        "args": {"type": "string", "description": "附带的参数/对象名，如日志的容器名、build 的 -t 名 . 、run 的镜像 命令"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 120"},
    },
    "required": ["action"],
}

REQUIRES = ["cli:docker"]  # 本机未装 docker 时自动停用


def run(action: str, args: str = "", timeout: int = 120) -> dict:
    import shutil
    docker = shutil.which("docker")
    if docker is None:
        return {"ok": False, "output": "未找到 docker CLI。请安装 Docker 后重试，或在设置页 tool_toggles 停用本工具。"}

    act = (action or "").strip().lower()
    a = (args or "").strip()
    timeout = max(5, min(int(timeout or 120), 900))

    cmd = {"ps": [docker, "ps"], "images": [docker, "images"],
           "logs": [docker, "logs", "--tail", "100", a], "inspect": [docker, "inspect", a],
           "build": [docker, "build", *a.split()], "run": [docker, "run", *a.split()],
           "stop": [docker, "stop", a], "remove": [docker, "rm", "-f", a],
           "compose": [docker, "compose", *a.split()]}
    if act not in cmd:
        return {"ok": False, "output": f"未知 action: {action}"}

    try:
        proc = subprocess.run(cmd[act], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, cwd=str(workspace_dir()))
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"docker 命令超时（>{timeout}s）"}
    except OSError as exc:
        return {"ok": False, "output": f"docker 执行失败: {exc}"}

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parts = [f"$ docker {' '.join(cmd[act][1:])}", f"exit_code: {proc.returncode}"]
    if out:
        parts.append(out[:8000])
    if err:
        parts.append("--- stderr ---\n" + err[:3000])
    return {"ok": proc.returncode == 0, "output": "\n".join(parts)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES", "DANGEROUS"]
