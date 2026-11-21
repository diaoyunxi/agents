#!/usr/bin/env python3
"""启动入口：读取 config.json 中的 host/port，启动 Web 服务（默认 6573 端口）。"""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

import config


def main() -> None:
    cfg = config.ensure_credentials()
    server = cfg.get("server", {}) or {}
    host = server.get("host", "127.0.0.1")
    port = int(server.get("port", 6573))
    config.workspace_dir()
    url = "http://{0}:{1}/".format("localhost" if host in ("0.0.0.0", "127.0.0.1") else host, port)
    auth = cfg.get("auth", {})
    print("=" * 62)
    print(" Agents 已启动: " + url)
    print(" 工作区: " + str(config.workspace_dir()))
    if not auth.get("setup_done"):
        print(" 初始账号: " + str(auth.get("username", "admin")) + " / " + str(auth.get("password", "(已自动生成)")))
        print(" 请尽快在设置页面中修改默认密码！")
    print("=" * 62)
    # 自动更新重启时由 updater.py 设置此变量，避免重复弹出浏览器
    if not os.environ.get("AGENTS_NO_BROWSER"):
        # 延迟 1 秒再开浏览器，确保服务已就绪
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
