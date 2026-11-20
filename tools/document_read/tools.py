"""读取多种文档格式为文本：PDF / Word(DOCX) / Markdown / 代码 / 文本（按格式降级）。"""

from __future__ import annotations

from pathlib import Path

from common import relative, resolve_path

NAME = "document_read"
DESCRIPTION = "读取文档为文本：PDF（需 pypdf）、Word/DOCX（需 python-docx）、Markdown/代码/文本（内置）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string", "description": "相对工作区的文档路径"},
        "format": {"type": "string", "description": "可选，强制指定 pdf/docx/md/code；省略则按扩展名判断"},
        "pages": {"type": "string", "description": "PDF 用：页码范围，如 `1` 或 `1-5`；省略为前 20 页"},
        "max_chars": {"type": "integer", "description": "最多返回的字符数，默认 20000"},
    },
    "required": ["filePath"],
}


def _pdf(path: Path, pages: str, max_chars: int) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"ok": False, "output": "未安装 pypdf，无法读取 PDF。请 `pip install pypdf`（或先用 python_execute 装）"}
    reader = PdfReader(str(path))
    total = len(reader.pages)
    lo = hi = None
    if pages:
        rng = (pages or "").strip()
        if "-" in rng:
            lo, hi = (int(x) for x in rng.split("-", 1))
        else:
            lo = hi = int(rng)
    lo = max(1, (lo or 1))
    hi = min(total, (hi or min(total, 20)))
    parts = [f"(第 {i} 页)" for i in range(lo, hi + 1)]
    text = "\n".join(f"===== {reader.pages[i-1].extract_text() or ''} =====" for i in range(lo, hi + 1))
    return {"output": f"PDF {relative(path)} | 共 {total} 页 | 显示 {lo}-{hi}\n{text[:max_chars]}"}


def _docx(path: Path, max_chars: int) -> dict:
    try:
        import docx
    except ImportError:
        return {"ok": False, "output": "未安装 python-docx，无法读取 DOCX。请 `pip install python-docx`"}
    d = docx.Document(str(path))
    text = "\n".join(p.text for p in d.paragraphs if p.text.strip())
    return {"output": f"DOCX {relative(path)}\n{text[:max_chars]}"}


def run(filePath: str, format: str = "", pages: str = "", max_chars: int = 20000) -> dict:
    try:
        target: Path = resolve_path(filePath, must_exist=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc)}
    max_chars = max(500, min(int(max_chars or 20000), 200000))
    fmt = (format or target.suffix.lstrip(".").lower()).lower()

    if fmt in ("pdf",):
        return _pdf(target, pages, max_chars)
    if fmt in ("docx", "doc", "word"):
        return _docx(target, max_chars)

    # 其余（md / txt / 代码 / json 等）用内置读法
    from common import read_text
    text = read_text(target, limit=max_chars)
    return {"output": f"文档 {relative(target)}（{fmt or 'text'}）\n{text}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
