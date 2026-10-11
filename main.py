"""启动入口：读取 config.json 中的 host/port，启动 Web 服务（默认 6573 端口）。"""

from __future__ import annotations

import os
import webbrowser

import uvicorn

import config


def main() -> None:
    cfg = config.load()
    server = cfg.get("server", {}) or {}
    host = server.get("host", "127.0.0.1")
    port = int(server.get("port", 6573))
    config.workspace_dir()
    url = "http://{0}:{1}/".format("localhost" if host in ("0.0.0.0", "127.0.0.1") else host, port)
    print("=" * 62)
    print(" Agents 已启动: " + url)
    print(" 工作区: " + str(config.workspace_dir()))
    auth = cfg.get("auth", {})
    username = auth.get("username", "root")
    if not auth.get("setup_done", False):
        print(f" 默认账号: {username}（首次登录后请立即修改密码）")
    else:
        print(f" 账号: {username}")
    print("=" * 62)
    # 自动更新重启时由 updater.py 设置此变量，避免重复弹出浏览器
    if not os.environ.get("AGENTS_NO_BROWSER"):
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run("app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
