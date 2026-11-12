"""工具元工具：查看某个工具的详细说明（含 schema、能力门控）。"""

from __future__ import annotations

from tools import loader

NAME = "tool_describe"
DESCRIPTION = "查看某个工具的详细说明（名称、描述、参数 schema、是否停用及原因）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "工具名，如 web_search"},
    },
    "required": ["name"],
}


def run(name: str) -> dict:
    item = loader.get_tool((name or "").strip())
    if item is None:
        return {"ok": False, "output": f"工具 `{name}` 不存在。可用: " + ", ".join(loader.registry())}
    enabled = loader.is_tool_enabled(item["name"])
    lines = [
        f"工具: {item['name']}",
        f"描述: {item.get('description', '')}",
        f"状态: {'启用' if enabled else '停用（缺能力: ' + ', '.join(item.get('capability_missing', [])) + '）'}",
    ]
    if item.get("requires"):
        lines.append("需要能力: " + ", ".join(item["requires"]))
    if item.get("dangerous"):
        lines.append("高风险: 是（DANGEROUS）")
    lines.append("\n参数 schema:\n" + __import__("json").dumps(item.get("parameters", {}), ensure_ascii=False, indent=2))
    if item.get("doc"):
        lines.append("\n说明文档:\n" + item["doc"])
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
