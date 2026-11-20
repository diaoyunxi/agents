"""比较两个文件/文本的差异（unified diff）。"""

from __future__ import annotations

import difflib

from common import SandboxError, read_text, relative, resolve_path

NAME = "diff_compare"
DESCRIPTION = "比较两个文件、或文件与给定文本之间的差异（unified diff），显示增删行"
PARAMETERS = {
    "type": "object",
    "properties": {
        "pathA": {"type": "string", "description": "第一个文件（相对工作区）"},
        "pathB": {"type": "string", "description": "第二个文件；可与 pathA 相同类型。也可省略，改用 textB 比较文件与文本"},
        "textA": {"type": "string", "description": "可选：直接用文本代替 pathA"},
        "textB": {"type": "string", "description": "可选：直接用文本代替 pathB"},
        "context": {"type": "integer", "description": "diff 上下文行数，默认 3"},
    },
    "required": ["pathA"],
}


def _read(path: str | None, text: str | None, label: str) -> tuple[list[str] | None, str]:
    if text is not None:
        return text.splitlines(), label
    if not path:
        return None, f"缺少 {label}：需提供 path 或 text"
    try:
        target = resolve_path(path, must_exist=True)
    except SandboxError as exc:
        return None, str(exc)
    return read_text(target).splitlines(), relative(target)


def run(pathA: str, pathB: str | None = None, textA: str | None = None,
        textB: str | None = None, context: int = 3) -> dict:
    a_lines, label_a = _read(pathA, textA, "pathA")
    if a_lines is None:
        return {"ok": False, "output": label_a}

    if pathB or textB is not None:
        b_lines, label_b = _read(pathB, textB, "pathB")
    else:
        b_lines, label_b = [], "(空)"
    if b_lines is None:
        return {"ok": False, "output": label_b}

    n = max(0, min(int(context or 3), 50))
    diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=label_a, tofile=label_b,
                                     lineterm="", n=n))
    if not diff:
        return {"output": f"两方内容完全一致：{label_a} 与 {label_b}"}
    additions = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    deletions = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    out = "\n".join(diff[:1500])
    if len(diff) > 1500:
        out += "\n... [diff 已截断]"
    return {"output": f"差异：+{additions} / -{deletions}\n{out}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
