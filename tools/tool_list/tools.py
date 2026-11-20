"""工具元工具：列出当前可用/全部工具及其能力门控状态。"""

from __future__ import annotations

from tools import loader

NAME = "tool_list"
DESCRIPTION = "列出当前可用工具（含被硬件/环境自动停用的），显示名称、说明、门控与启用状态"
PARAMETERS = {
    "type": "object",
    "properties": {
        "include_disabled": {"type": "boolean", "description": "是否同时列出因缺能力被停用的工具，默认 true"},
    },
    "required": [],
}


def run(include_disabled: bool = True) -> dict:
    all_tools = loader.list_tools()
    lines = []
    for t in all_tools:
        if not include_disabled and not t.get("enabled", True):
            continue
        flag = "启用" if t.get("enabled", True) else "停用(缺能力)"
        lines.append(f"[{flag}] {t['name']} —— {t.get('description', '')}")
        if not t.get("capability_ok", True):
            lines.append(f"      缺能力: {', '.join(t.get('capability_missing', []))}")
    header = f"共 {len(loader.list_tools())} 个工具，其中 {sum(1 for t in loader.list_tools() if t.get('enabled'))} 个当前可用"
    return {"output": header + "\n" + "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
