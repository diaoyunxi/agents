"""批量补齐所有缺失的 Python 依赖：扫描被门控停用的工具，一键安装缺的包。

与 pip_install 的区别：pip_install 是通用安装；fix_capabilities 面向「让被自动停用的工具恢复」，
自动收集所有工具的 REQUIRES 里未满足的 pkg: 项，一次安装。
"""

from __future__ import annotations

from common import workspace_dir

NAME = "fix_capabilities"
DANGEROUS = True
DESCRIPTION = "扫描被门控停用的工具，自动收集缺失的 Python 包并批量 pip install，装完刷新缓存使工具恢复启用"
PARAMETERS = {
    "type": "object",
    "properties": {
        "only": {
            "type": "array",
            "description": "可选：只修这些工具缺失的包（工具名列表）；省略则修全部",
            "items": {"type": "string"},
        },
        "dry_run": {
            "type": "boolean",
            "description": "true 时只列出要装的包，不实际安装，默认 false",
        },
        "timeout": {
            "type": "integer",
            "description": "超时秒数，默认 600，最大 1800",
        },
    },
    "required": [],
}


def run(only: list[str] | None = None, dry_run: bool = False, timeout: int = 600) -> dict:
    from tools import loader
    from capabilities import has

    all_tools = loader.list_tools()
    disabled = [t for t in all_tools if not t.get("enabled", True)]
    if only:
        names = {n.lower() for n in only if isinstance(n, str)}
        disabled = [t for t in disabled if t["name"].lower() in names]

    missing_pkgs: list[str] = []
    affected: list[tuple[str, list[str]]] = []
    for t in disabled:
        missing = t.get("capability_missing") or []
        # 只处理 pkg: 前缀（CLI/GPU 等非 pip 包不在这装）
        pkg_tags = [m.split(":", 1)[1].strip() for m in missing
                    if isinstance(m, str) and m.startswith("pkg:")]
        # 排除已经可用的
        pkg_tags = [p for p in pkg_tags if p and not has(f"pkg:{p}")]
        if pkg_tags:
            affected.append((t["name"], pkg_tags))
            for p in pkg_tags:
                if p not in missing_pkgs:
                    missing_pkgs.append(p)

    header = "被门控停用的工具及缺失包：\n"
    if affected:
        for name, tags in affected:
            header += f"  - {name}: {', '.join('pip install ' + t for t in tags)}\n"
    else:
        header += "  （无缺失 Python 包；可能缺 CLI/GPU 等非 pip 能力，或全部已满足）"

    if not missing_pkgs:
        return {"output": header + "\n无需安装 Python 包。"}

    if dry_run:
        return {"output": header + f"\n\n[dry-run] 将执行: pip install {' '.join(missing_pkgs)}（未实际安装）"}

    # 调用 pip_install 工具执行安装
    from tools import loader as tl
    pip_tool = tl.get_tool("pip_install")
    if pip_tool is None:
        return {"ok": False, "output": header + "\n（pip_install 工具不可用，无法自动安装）"}
    timeout = max(60, min(int(timeout or 600), 1800))
    result = pip_tool["run"](packages=missing_pkgs, timeout=timeout)
    extra = ""
    if result.get("ok"):
        # 刷新缓存并统计恢复情况
        import capabilities
        capabilities.refresh()
        recovered = []
        for name, _ in affected:
            if tl.get_tool(name) and tl.is_tool_enabled(name):
                recovered.append(name)
        extra = ("\n\n✓ 安装成功，已刷新能力缓存。恢复启用的工具: "
                 + (", ".join(recovered) if recovered else "（无新增恢复）"))
    return {"ok": bool(result.get("ok", False)),
            "output": header + f"\n\n安装 {len(missing_pkgs)} 个包: {' '.join(missing_pkgs)}\n{result.get('output', '')}{extra}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "DANGEROUS"]
