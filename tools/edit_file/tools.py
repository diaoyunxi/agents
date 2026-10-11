"""对工作区文件做精确的字符串替换 / 追加 / 删除行。"""

from __future__ import annotations

from pathlib import Path

from common import SandboxError, read_text, record_change, relative, resolve_path

NAME = "edit_file"
DESCRIPTION = "在工作区文件中做精确的查找替换、追加内容或按行删除，并记录 diff"
PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作区的目标文件路径"},
        "old_string": {"type": "string", "description": "要被替换的原文，必须精确匹配（mode=replace 时必填）"},
        "new_string": {"type": "string", "description": "替换后的新文本；为空表示删除（mode=replace）"},
        "replace_all": {"type": "boolean", "description": "是否替换全部出现，默认 false"},
        "mode": {"type": "string", "description": "replace（默认）/ append / prepend / delete_lines"},
        "start_line": {"type": "integer", "description": "delete_lines 模式的起始行号（从 1 开始）"},
        "end_line": {"type": "integer", "description": "delete_lines 模式的结束行号（含）"},
        "content": {"type": "string", "description": "append/prepend 模式要插入的文本"},
    },
    "required": ["path"],
}


def run(
    path: str,
    old_string: str | None = None,
    new_string: str | None = None,
    replace_all: bool = False,
    mode: str = "replace",
    start_line: int | None = None,
    end_line: int | None = None,
    content: str | None = None,
) -> dict:
    target: Path = resolve_path(path, must_exist=True)
    if target.is_dir():
        raise SandboxError(f"{relative(target)} 是目录，无法编辑")
    before = read_text(target)
    rel = relative(target)
    mode = (mode or "replace").lower()

    if mode == "replace":
        if not old_string:
            return {"ok": False, "output": "mode=replace 时必须提供 old_string"}
        if old_string not in before:
            hint = _closest_hint(before, old_string)
            return {"ok": False, "output": f"在 {rel} 中未找到待替换文本。{hint}"}
        count = before.count(old_string)
        after = before.replace(old_string, new_string or "", -1 if replace_all else 1)
        done = count if replace_all else 1
    elif mode in ("append", "prepend"):
        text = content if content is not None else (new_string or "")
        if not text:
            return {"ok": False, "output": f"mode={mode} 时必须提供 content 或 new_string"}
        if not text.endswith("\n"):
            text += "\n"
        after = text + before if mode == "prepend" else before + text
        done = 1
    elif mode == "delete_lines":
        if start_line is None or end_line is None:
            return {"ok": False, "output": "mode=delete_lines 时必须提供 start_line 与 end_line"}
        lines = before.splitlines(keepends=True)
        begin, finish = max(1, int(start_line)), min(len(lines), int(end_line))
        if begin > len(lines):
            return {"ok": False, "output": f"起始行 {begin} 超出文件行数 {len(lines)}"}
        removed = lines[begin - 1 : finish]
        after = "".join(lines[: begin - 1] + lines[finish:])
        done = finish - begin + 1
        del removed
    else:
        return {"ok": False, "output": f"未知 mode: {mode}（可选 replace/append/prepend/delete_lines）"}

    if after == before:
        return {"ok": False, "output": f"{rel} 内容未发生变化"}

    target.write_text(after, encoding="utf-8")
    record_change(target, "modify", before=before, after=after)
    return {"output": f"已编辑 {rel}（{mode}，影响 {done} 处）"}


def _closest_hint(text: str, old_string: str) -> str:
    """当精确匹配失败时，给出最接近的一行，节省一轮往返。"""

    target_line = (old_string or "").strip().splitlines()
    needle = target_line[0].strip() if target_line else ""
    if not needle:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if line.strip() == needle:
            return f"疑似位于第 {i} 行，内容完全一致，请检查缩进或前后空行。"
    close = difflib_close(needle, lines)
    if close:
        idx, line = close
        return f"最接近的是第 {idx} 行：`{line.strip()}`，请核对缩进/空格。"
    return ""


def difflib_close(needle: str, lines: list[str]):
    import difflib

    best, best_ratio = None, 0.0
    for i, line in enumerate(lines, 1):
        ratio = difflib.SequenceMatcher(None, needle, line.strip()).ratio()
        if ratio > best_ratio:
            best, best_ratio = (i, line), ratio
    return best if best_ratio >= 0.85 else None


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
