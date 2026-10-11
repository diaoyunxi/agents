"""独立的自更新重启器（由 Web 服务以“分离进程”方式启动）。

为什么必须是独立进程？
    Python 在启动时会把源码读入并编译进内存，之后运行不再依赖磁盘上的 .py
    文件。因此本进程一旦被拉起，即使随后 git 把磁盘上的源码（包括本文件自己）
    替换甚至删除，内存中的代码依然可以继续执行，足以走完
    “等待旧服务退出 → 拉取新代码 → 拉起新服务进程”这一完整闭环。

    反之若由 Web 服务进程自己执行，则会在覆盖自身文件、释放端口、重启自己时
    陷入句柄与地址冲突；把这段逻辑“搬到一个已经加载完毕的旁路进程”里，就绕开
    了自举（bootstrap）难题。

参数：
    --pid    旧服务进程 PID（更新完成后需要它先退出）
    --cwd    仓库根目录
    --port   Web 服务端口（用于探活）
    --delay  启动后先等待的秒数（给旧进程把 HTTP 响应发回浏览器）
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LOG_NAME = ".updater.log"
RESULT_NAME = ".updater_result.json"


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def _log(path: Path, message: str) -> None:
    line = "[{}] {}".format(time.strftime("%Y-%m-%d %H:%M:%S"), message)
    print(line, flush=True)
    try:
        with open(path, "a", encoding="utf-8") as handle:
            _ = handle.write(line + "\n")
    except OSError:
        pass


def _detach_flags() -> int:
    if os.name == "nt":
        return (subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW)
    return 0


def _pid_alive(pid: int) -> bool:
    """判断进程是否仍存活（跨平台）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill(pid: int) -> None:
    """强制结束指定进程。注意：不带 /T，避免连坐杀掉本更新器自身。"""
    if pid <= 0:
        return
    if os.name == "nt":
        _ = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           check=False, capture_output=True, env=os.environ)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _wait_pid_exit(pid: int, timeout: float, log_path: Path) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.25)
    _log(log_path, "等待 PID {} 退出超时".format(pid))
    return not _pid_alive(pid)


def _run(cmd: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    for key, value in (("GIT_OPTIONAL_LOCKS", "0"), ("LANG", "C.UTF-8"), ("LC_ALL", "C.UTF-8")):
        if key not in env:
            env[key] = value
    try:
        proc = subprocess.run(cmd, check=False, cwd=str(cwd), capture_output=True,
                              timeout=timeout, env=env)
    except FileNotFoundError:
        return -1, "未找到命令：{}".format(cmd[0])
    except subprocess.TimeoutExpired:
        return -2, "命令超时：{}".format(" ".join(cmd))
    out = proc.stdout.decode("utf-8", "replace").strip()
    err = proc.stderr.decode("utf-8", "replace").strip()
    return proc.returncode, (out + ("\n" if out and err else "") + err).strip()


def _short_head(cwd: Path) -> str:
    code, text = _run(["git", "rev-parse", "--short", "HEAD"], cwd, 15)
    return text if code == 0 else ""


def _update_code(cwd: Path, log_path: Path) -> tuple[bool, str]:
    """拉取新代码。拆成 fetch + merge，并为 fetch 设短超时，
    这样网络不通时可以快速失败，避免服务长时间处于停机状态。"""
    code, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd, 10)
    if code != 0 or not branch or branch == "HEAD":
        branch = ""
    code, remotes = _run(["git", "remote"], cwd, 10)
    names = remotes.split()
    remote = "origin" if "origin" in names else (names[0] if names else "")
    if not remote:
        return False, "未配置远程仓库，跳过更新"

    args = ["git", "fetch", "--quiet", "--no-tags", remote]
    if branch:
        args.append(branch)
    code, out = _run(args, cwd, 20)
    if code != 0:
        return False, "fetch 失败：" + out

    code, out = _run(["git", "merge", "--ff-only", "--no-edit", "FETCH_HEAD"], cwd, 20)
    if code != 0:
        return False, "merge 失败：" + out
    _log(log_path, "代码更新完成：{}".format(out or "已是新版本"))
    return True, out or "已是最新"


def _wait_http(port: int, timeout: float) -> bool:
    url = "http://127.0.0.1:{}/api/health".format(port)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def _launch(cwd: Path, log_path: Path) -> "subprocess.Popen[bytes]":
    """拉起新的 Web 服务进程（同样以分离方式，确保其不受本进程退出影响）。"""
    env = dict(os.environ)
    env["AGENTS_NO_BROWSER"] = "1"       # 重启时不要再自动弹出浏览器
    env["AGENTS_UPDATED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    handle = open(log_path, "a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(cwd / "main.py")],
        cwd=str(cwd),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=_detach_flags(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Agents 自更新重启器")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--port", type=int, default=6573)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    log_path = cwd / LOG_NAME
    result_path = cwd / RESULT_NAME

    _log(log_path, "更新器启动 pid={} 待退役进程={} 端口={}".format(
        os.getpid(), args.pid, args.port))

    # 0. 稍等片刻，让旧服务把「已触发更新」的响应发回浏览器
    time.sleep(max(0.0, args.delay))

    # 1. 等旧服务退出，必要时强制结束，确保旧代码与端口都被释放
    if args.pid > 0:
        _log(log_path, "等待旧服务 PID {} 退出…".format(args.pid))
        if not _wait_pid_exit(args.pid, 15, log_path):
            _log(log_path, "旧服务未按时退出，强制结束")
            _kill(args.pid)
            _ = _wait_pid_exit(args.pid, 6, log_path)

    # 2. 拉取新代码（失败不阻塞重启，按原代码重新拉起，保证服务可用）
    before = _short_head(cwd)
    ok, output = _update_code(cwd, log_path)
    after = _short_head(cwd)
    updated = ok and after != before
    _log(log_path, "拉取结果 ok={} {} -> {}\n{}".format(ok, before, after, output))

    # 3. 拉起新服务进程，并探活；失败则重试
    restarted = False
    message = ""
    head = _short_head(cwd)
    for attempt in range(1, 4):
        _log(log_path, "第 {} 次拉起新服务…".format(attempt))
        proc = _launch(cwd, log_path)
        if _wait_http(args.port, 30):
            restarted = True
            _log(log_path, "服务已恢复 (pid={})".format(proc.pid))
            break
        _log(log_path, "服务未在 30s 内就绪，退出码={}，准备重试".format(proc.poll()))

    if restarted:
        if updated:
            message = "更新完成：{} → {}，服务已重启".format(before or "?", head or "?")
        elif ok:
            message = "代码已是最新（{}），服务已重启".format(head or "?")
        else:
            message = "拉取失败，已按原代码重启服务"
    else:
        message = "服务重启失败，请手动运行 main.py"

    result = {
        "ok": restarted,
        "updated": updated,
        "restarted": restarted,
        "git_ok": ok,
        "git_output": output,
        "from": before,
        "to": head,
        "message": message,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        _ = result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    except OSError:
        pass

    _log(log_path, message)
    return 0 if restarted else 1


if __name__ == "__main__":
    sys.exit(main())
