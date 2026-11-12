"""技能（Skills）加载器：skills/ 下一个 .md 文件即一个技能，文件名即技能名。"""

from __future__ import annotations

import re
from pathlib import Path

from config import skills_dir

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_meta(raw: str, name: str) -> dict:
    """支持可选的 front-matter：name / description / when_to_use。"""

    meta = {"name": name, "description": "", "when_to_use": ""}
    match = _FRONTMATTER.match(raw)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                if key in meta:
                    meta[key] = value.strip().strip("\"'")
        raw = raw[match.end():]
    if not meta["description"]:
        head = next((ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith("#")), "")
        meta["description"] = head[:120]
    return meta


def load_skills(names=None):
    """加载技能。`names` 为 None 时加载全部；为列表时只返回名称命中且存在的技能。"""
    root = skills_dir()
    root.mkdir(parents=True, exist_ok=True)
    skills = []
    for path in sorted(root.glob("*.md")):
        if path.name.lower() in ("readme.md", "index.md"):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta = _parse_meta(raw, path.stem)
        skills.append({
            "name": meta["name"],
            "description": meta["description"],
            "when_to_use": meta["when_to_use"],
            "content": raw.strip(),
            "path": str(path),
        })
    if names is None:
        return skills
    wanted = [n for n in (names or []) if n]
    return [s for s in skills if s["name"] in wanted]


def skill_names() -> list:
    """返回所有已加载技能的名称（稳定排序）。"""
    return [s["name"] for s in load_skills()]


def build_prompt_section(names=None) -> str:
    """组装技能文档。`names` 为 None 时包含全部技能；为列表（可为空）时只包含列出的技能。"""
    skills = load_skills(None if names is None else names)
    if not skills:
        return ""
    parts = ["## 技能库（Skills）\n\n以下是本项目提供的技能文档。当任务与某个技能相关时，遵循对应技能的流程与约束。"]
    for skill in skills:
        head = "### 技能 `" + skill["name"] + "`"
        if skill["description"]:
            head += " —— " + skill["description"]
        parts.append(head + "\n" + skill["content"])
    return "\n\n".join(parts)


def skills_root() -> Path:
    return skills_dir()
