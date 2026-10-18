"""加载可请求的工作区 / 项目规则（.agents/rules/ 下的 md 文件）。"""

from __future__ import annotations

from pathlib import Path

from config import BASE_DIR
from common import workspace_dir

NAME = "read_rules"
DESCRIPTION = "按需加载可请求的规则文档（工作区与项目 .agents/rules/ 下的 md）；不带参数时列出全部可用规则"
PARAMETERS = {
    "type": "object",
    "properties": {
        "ruleNames": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要加载的规则键（绝对路径或文件名/去扩展名）；省略则只列出可用规则",
        },
    },
    "required": [],
}

RULE_DIRS = (".agents/rules", ".codebuddy/rules")


def _rule_dirs() -> list[Path]:
    dirs: list[Path] = []
    for root in (workspace_dir(), BASE_DIR):
        for rel in RULE_DIRS:
            candidate = Path(root) / rel
            if candidate.is_dir():
                dirs.append(candidate)
    return dirs


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """解析可选的 front-matter（--- 之间的 key: value 行）。"""

    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
            body = parts[2].lstrip("\n")
    return meta, body


def _discover() -> list[dict]:
    rules: list[dict] = []
    seen: set[str] = set()
    for folder in _rule_dirs():
        for md in sorted(folder.glob("*.md")):
            key = str(md.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                meta, _body = _parse_front_matter(md.read_text(encoding="utf-8"))
            except OSError:
                continue
            rules.append({
                "key": key,
                "name": meta.get("name") or md.stem,
                "description": meta.get("description") or "",
                "when_to_use": meta.get("when_to_use") or "",
            })
    return rules


def _resolve_key(name: str, rules: list[dict]) -> dict | None:
    name = (name or "").strip()
    if not name:
        return None
    for rule in rules:
        if rule["key"] == name or rule["name"] == name:
            return rule
    stem = name[:-3] if name.lower().endswith(".md") else name
    for rule in rules:
        if Path(rule["key"]).stem == stem:
            return rule
    return None


def run(ruleNames: list[str] | None = None) -> dict:
    rules = _discover()
    if not rules:
        return {"output": (
            "未找到任何规则文件。规则放在 `<工作区>/.agents/rules/*.md`（或项目目录下同名路径），"
            "每个文件可带 front-matter：name / description / when_to_use。")}

    names = [str(n).strip() for n in (ruleNames or []) if str(n).strip()]
    if not names:
        lines = ["可用规则（用 ruleNames 指定键来加载）："]
        for rule in rules:
            desc = rule["description"] or rule["when_to_use"] or "（无描述）"
            lines.append(f"- {rule['name']}  [{rule['key']}]\n    {desc}")
        return {"output": "\n".join(lines)}

    chunks = []
    missing = []
    for name in names:
        rule = _resolve_key(name, rules)
        if rule is None:
            missing.append(name)
            continue
        try:
            text = Path(rule["key"]).read_text(encoding="utf-8")
        except OSError as exc:
            missing.append(f"{name}（读取失败: {exc}）")
            continue
        _meta, body = _parse_front_matter(text)
        chunks.append(f"===== 规则 {rule['name']}（{rule['key']}）=====\n{body.strip()}")
    if missing:
        chunks.append("未找到的规则键: " + ", ".join(missing)
                      + "；可用键见上方列表（不带参数调用本工具可重新列出）。")
    return {"output": "\n\n".join(chunks)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
