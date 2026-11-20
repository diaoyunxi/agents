"""生成结构化 Markdown 报告并写入工作区文件（无额外依赖）。"""

from __future__ import annotations

import datetime
from pathlib import Path

from common import record_change, relative, workspace_dir

NAME = "report_generate"
DESCRIPTION = "把已收集到的信息组织成结构化 Markdown 报告并保存到工作区（可含标题/要点/表格/结论）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "报告标题"},
        "sections": {
            "type": "array",
            "description": "报告章节数组，每项 {\"heading\": \"章节名\", \"content\": \"内容（支持 Markdown）\"}",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string", "description": "章节标题"},
                    "content": {"type": "string", "description": "章节正文（Markdown）"},
                },
                "required": ["heading", "content"],
            },
        },
        "conclusion": {"type": "string", "description": "结论/建议（可选，Markdown）"},
        "outputPath": {"type": "string", "description": "输出文件路径（相对工作区），默认 report_YYYYMMDD-HHMMSS.md"},
    },
    "required": ["title", "sections"],
}


def run(title: str, sections: list, conclusion: str = "", outputPath: str = "") -> dict:
    title = (title or "").strip()
    if not title:
        return {"ok": False, "output": "title 不能为空"}
    if not isinstance(sections, list) or not sections:
        return {"ok": False, "output": "sections 不能为空（至少 1 个章节）"}

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_rel = outputPath or f"report_{stamp}.md"
    target: Path = workspace_dir().resolve() / out_rel
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# {title}", "", f"> 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading", "") or "").strip()
        content = str(sec.get("content", "") or "").strip()
        lines += [f"## {heading or '（未命名章节）'}", "", content, ""]
    if (conclusion or "").strip():
        lines += ["## 结论与建议", "", conclusion.strip(), ""]
    body = "\n".join(lines).rstrip() + "\n"

    target.write_text(body, encoding="utf-8")
    record_change(target, "create")
    return {"output": f"已生成报告 {relative(target)}（{len(sections)} 章节，{len(body)} 字符）"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
