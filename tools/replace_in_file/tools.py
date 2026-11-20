"""对工作区文件做精确的字符串替换。"""

from __future__ import annotations

from pathlib import Path

from common import SandboxError, read_text, record_change, relative, resolve_path

NAME = "replace_in_file"
DESCRIPTION = "在已有文件中做精确的字符串查找替换（含缩进必须完全一致），变更会记录到文件变更面板"
PARAMETERS = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string", "description": "相对工作区的目标文件路径，必须已存在"},
        "old_string": {"type": "string", "description": "要被替换的原文，必须与文件内容精确一致（含缩进与空行）"},
        "new_string": {"type": "string", "description": "替换后的新文本；省略或留空表示删除这段内容"},
        "replace_all": {"type": "boolean", "description": "是否替换全部出现的位置，默认 false（只替换第一处）"},
    },
    "required": ["filePath", "old_string"],
}


def _adapt_line_endings(before: str, old_string: str) -> tuple[str | None, bool]:
    """行尾容错：文件为 CRLF 而 old_string 用 LF（或反之）时，在归一化文本上匹配。

    返回 (用于匹配与替换的文本, 是否做过归一化)；不匹配时返回 (None, False)。
    """

    if old_string in before:
        return before, False
    if "\r\n" in before or "\r\n" in old_string:
        norm = before.replace("\r\n", "\n")
        if old_string.replace("\r\n", "\n") in norm:
            return norm, True
    return None, False


def run(filePath: str, old_string: str, new_string: str | None = None, replace_all: bool = False) -> dict:
    if not old_string:
        return {"ok": False, "output": "old_string 不能为空（删除请改用 delete_file 或把 new_string 留空并给出待删原文）"}
    try:
        target: Path = resolve_path(filePath, must_exist=True)
    except SandboxError as exc:
        return {"ok": False, "output": str(exc)}
    if target.is_dir():
        return {"ok": False, "output": f"{relative(target)} 是目录，无法编辑"}

    before = read_text(target)
    rel = relative(target)
    crlf_file = "\r\n" in before

    work, normalized = _adapt_line_endings(before, old_string)
    if work is None:
        hint = _closest_hint(before, old_string)
        return {"ok": False, "output": f"在 {rel} 中未找到待替换文本。{hint}"}

    needle = old_string.replace("\r\n", "\n") if normalized else old_string
    count = work.count(needle)
    if not replace_all and count > 1:
        return {"ok": False, "output": (
            f"在 {rel} 中找到 {count} 处相同的 old_string。为避免误改，请补充更多上下文使其唯一，"
            "或显式设置 replace_all=true 全部替换。")}
    after = work.replace(needle, (new_string or "").replace("\r\n", "\n") if normalized else (new_string or ""),
                         -1 if replace_all else 1)
    done = count if replace_all else 1

    if after == work:
        return {"ok": False, "output": f"{rel} 内容未发生变化"}

    # 还原原文件的换行风格，避免整文件行尾漂移造成巨大 diff
    if normalized and crlf_file:
        after = after.replace("\r\n", "\n").replace("\n", "\r\n")
    try:
        target.write_bytes(after.encode("utf-8"))
    except OSError as exc:
        return {"ok": False, "output": f"写入失败: {rel}（{exc}）"}

    record_change(target, "modify", before=before, after=after)
    return {"output": f"已编辑 {rel}（替换 {done} 处）"}


def _closest_hint(text: str, old_string: str) -> str:
    """精确匹配失败时给出最接近的一行，节省一轮往返。"""

    import difflib

    target_lines = (old_string or "").strip().splitlines()
    needle = target_lines[0].strip() if target_lines else ""
    if not needle:
        return ""
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if line.strip() == needle:
            return f"疑似位于第 {i} 行，内容完全一致，请检查缩进或前后空行。"
    best, best_ratio = None, 0.0
    for i, line in enumerate(lines, 1):
        ratio = difflib.SequenceMatcher(None, needle, line.strip()).ratio()
        if ratio > best_ratio:
            best, best_ratio = (i, line), ratio
    if best and best_ratio >= 0.85:
        return f"最接近的是第 {best[0]} 行：`{best[1].strip()}`，请核对缩进/空格。"
    return ""


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
