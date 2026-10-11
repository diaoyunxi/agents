"""启动入口：读取 config.json 中的 host/port，启动 Web 服务（默认 6573 端口）。"""

from __future__ import annotations

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
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    uvicorn.run("app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
