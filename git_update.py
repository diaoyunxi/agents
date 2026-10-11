"""Git 自更新支持：检查远端新提交，并以“分离进程”方式触发更新与重启。

设计原则：
- 检查阶段只做只读操作（git status / fetch / rev-list），绝不改动工作区。
- 更新阶段不在 Web 服务进程内执行 git 与重启，而是把这两件事交给独立的
  updater.py 进程去做，从而让 Web 服务进程可以在更新过程中被安全替换。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPDATER = BASE_DIR / "updater.py"
RESULT_FILE = BASE_DIR / ".updater_result.json"
LOG_FILE = BASE_DIR / ".updater.log"

# fetch 的防抖缓存：成功后短缓存，失败后长缓存，避免网络不通时反复卡顿
FETCH_TTL_OK = 10.0
FETCH_TTL_FAIL = 90.0
FETCH_TIMEOUT = 15.0
_fetch_lock = threading.Lock()
_fetch_cache: dict = {"ts": 0.0, "key": "", "data": (False, "")}

_state_lock = threading.Lock()
_updating = False


# --------------------------------------------------------------------------- #
# 基础 git 调用
# --------------------------------------------------------------------------- #


def _env() -> dict:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # 禁止弹出账号密码交互，避免卡死
    env.setdefault("GIT_OPTIONAL_LOCKS", "0")
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    return env


def _git(args: list[str], timeout: float = 30.0, cwd: Path | None = None) -> tuple[int, str, str]:
    """执行 git 命令，返回 (returncode, stdout, stderr)。"""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd or BASE_DIR),
            capture_output=True,
            timeout=timeout,
            env=_env(),
        )
    except FileNotFoundError:
        return -1, "", "未找到 git 命令，请先安装 Git 并加入 PATH"
    except subprocess.TimeoutExpired:
        return -2, "", "git {} 执行超时".format(" ".join(args))
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace").strip()
    return proc.returncode, out, err


def is_repo() -> bool:
    code, out, _ = _git(["rev-parse", "--is-inside-work-tree"], timeout=10)
    return code == 0 and out.strip() == "true"


def _branch() -> str:
    code, out, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
    if code == 0 and out and out != "HEAD":
        return out
    return ""


def _remote(branch: str) -> str:
    if branch:
        code, out, _ = _git(["config", "--get", "branch.{}.remote".format(branch)], timeout=10)
        if code == 0 and out:
            return out
    code, out, _ = _git(["remote"], timeout=10)
    remotes = [line.strip() for line in out.splitlines() if line.strip()]
    if "origin" in remotes:
        return "origin"
    return remotes[0] if remotes else ""


def _upstream(branch: str) -> str:
    code, out, _ = _git(["rev-parse", "--abbrev-ref", "{}@{{u}}".format(branch)], timeout=10)
    return out if code == 0 and out else ""


def _fetch(remote: str, branch: str, force: bool = False) -> tuple[bool, str]:
    """拉取远程分支引用。同一分支在 TTL 内复用结果，避免网络风暴。"""
    key = "{}/{}".format(remote, branch)
    now = time.time()
    with _fetch_lock:
        cached = _fetch_cache["data"]
        ttl = FETCH_TTL_OK if cached[0] else FETCH_TTL_FAIL
        if (not force and _fetch_cache["key"] == key
                and now - _fetch_cache["ts"] < ttl):
            return cached
        args = ["fetch", "--quiet", "--no-tags", remote]
        if branch:
            args.append(branch)
        code, out, err = _git(args, timeout=FETCH_TIMEOUT)
        result = (code == 0, (err or out) or "")
        _fetch_cache["ts"] = now
        _fetch_cache["key"] = key
        _fetch_cache["data"] = result
        return result


# --------------------------------------------------------------------------- #
# 状态检查（每次访问 web 都会调用）
# --------------------------------------------------------------------------- #


def info(force_fetch: bool = False) -> dict:
    """检查远端是否有新提交。

    返回字段中 has_update 表示是否有可拉取的提交；dirty 表示工作区是否有
    未提交改动（等价于 git status 的结果）。
    """
    result: dict = {
        "is_repo": False,
        "branch": "",
        "remote": "",
        "local_head": "",
        "remote_head": "",
        "behind": 0,
        "ahead": 0,
        "has_update": False,
        "dirty": False,
        "commits": [],
        "fetched": False,
        "error": "",
        "updating": _updating,
    }
    if not is_repo():
        result["error"] = "当前目录不是 Git 仓库，无法自动更新"
        return result
    result["is_repo"] = True

    branch = _branch()
    result["branch"] = branch
    if not branch:
        result["error"] = "处于游离 HEAD 状态，无法检查更新"
        return result

    # 每次访问都执行一次 git status（本地只读，开销极小）
    code, out, _ = _git(["status", "--porcelain"], timeout=15)
    result["dirty"] = bool(out.strip()) if code == 0 else False

    code, out, _ = _git(["rev-parse", "--short", "HEAD"], timeout=10)
    result["local_head"] = out if code == 0 else ""

    remote = _remote(branch)
    result["remote"] = remote
    if not remote:
        result["error"] = "未配置远程仓库"
        return result

    ok, fetch_err = _fetch(remote, branch, force=force_fetch)
    result["fetched"] = ok
    if not ok:
        result["error"] = "获取远程信息失败：" + (fetch_err or "未知错误")
        return result

    upstream = _upstream(branch) or "{}/{}".format(remote, branch)
    code, remote_head, _ = _git(["rev-parse", "--short", upstream], timeout=10)
    if code != 0:
        result["error"] = "未找到远程分支 {}".format(upstream)
        return result
    result["remote_head"] = remote_head

    code, behind, _ = _git(["rev-list", "--count", "HEAD..{}".format(upstream)], timeout=15)
    result["behind"] = int(behind) if code == 0 and behind.isdigit() else 0

    code, ahead, _ = _git(["rev-list", "--count", "{}..HEAD".format(upstream)], timeout=15)
    result["ahead"] = int(ahead) if code == 0 and ahead.isdigit() else 0

    result["has_update"] = result["behind"] > 0
    if result["has_update"]:
        code, log, _ = _git(
            ["log", "--no-decorate", "--pretty=format:%h|%s|%an|%ar", "-n", "20",
             "HEAD..{}".format(upstream)],
            timeout=15,
        )
        if code == 0 and log:
            commits = []
            for line in log.splitlines():
                parts = line.split("|", 3)
                commits.append({
                    "hash": parts[0],
                    "subject": parts[1] if len(parts) > 1 else "",
                    "author": parts[2] if len(parts) > 2 else "",
                    "when": parts[3] if len(parts) > 3 else "",
                })
            result["commits"] = commits
    return result


# --------------------------------------------------------------------------- #
# 触发更新：交给独立的 updater.py 进程
# --------------------------------------------------------------------------- #


def _detach_flags() -> int:
    """让子进程完全脱离当前进程（Windows 无控制台、独立进程组）。"""
    if os.name == "nt":
        return (subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW)
    return 0


def _server_port() -> int:
    try:
        import config
        return int(config.get("server.port", 6573))
    except Exception:  # noqa: BLE001
        return 6573


def start_update(delay: float = 2.0) -> dict:
    """以分离进程方式启动 updater.py；调用方应在返回后自行退出。"""
    global _updating
    with _state_lock:
        if _updating:
            return {"ok": False, "message": "已有更新任务正在进行中"}
        if not UPDATER.exists():
            return {"ok": False, "message": "缺少 updater.py，无法自动更新"}
        _updating = True

    try:
        RESULT_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    cmd = [
        sys.executable, str(UPDATER),
        "--pid", str(os.getpid()),
        "--cwd", str(BASE_DIR),
        "--port", str(_server_port()),
        "--delay", str(delay),
    ]
    log_handle = open(LOG_FILE, "a", encoding="utf-8")
    log_handle.write("\n===== {} 触发更新 (old_pid={}) =====\n".format(
        time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid()))
    log_handle.flush()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=_detach_flags(),
        )
    except Exception as exc:  # noqa: BLE001
        _updating = False
        log_handle.close()
        return {"ok": False, "message": "启动更新进程失败：{}".format(exc)}
    log_handle.close()
    return {"ok": True, "message": "已启动更新进程", "updater_pid": proc.pid}


def read_result() -> dict:
    """读取上一次更新的结果（供前端在服务重启后展示）。"""
    if not RESULT_FILE.exists():
        return {}
    try:
        return json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def is_updating() -> bool:
    return _updating
