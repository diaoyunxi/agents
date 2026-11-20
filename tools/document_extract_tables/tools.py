"""从文档/表格中提取表格：CSV/TSV（内置总可用）、XLSX（需 openpyxl，未装则停用该项）。"""

from __future__ import annotations

from pathlib import Path

from common import relative, resolve_path

NAME = "document_extract_tables"
DESCRIPTION = "提取表格：CSV/TSV 直接解析（内置）；XLSX 需 openpyxl；可按索引取第 N 个表"
PARAMETERS = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string", "description": "表格文件路径（csv/tsv/xlsx）"},
        "table_index": {"type": "integer", "description": "XLSX 用：取第几个工作表（0 起），默认 0"},
        "limit": {"type": "integer", "description": "最多返回的行数，默认 50"},
    },
    "required": ["filePath"],
}

# XLSX 需 openpyxl；缺失时本工具仍可解析 CSV/TSV，故不整体门控，仅对 xlsx 降级
REQUIRES = []  # 留空 = 总是可用；xlsx 能力在调用期按库缺失降级


def _parse_delimited(path: Path, limit: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    first = next((l for l in text.splitlines() if l.strip()), "")
    sep = "\t" if "\t" in first else (";" if first.count(";") > first.count(",") else ",")
    lines = [l for l in text.splitlines() if l.strip()][:limit]
    cells = [l.split(sep) for l in lines]
    body = "\n".join("\t".join(c) for c in cells)
    return f"（分隔符: {repr(sep)}，显示 {len(cells)} 行）\n{body}"


def run(filePath: str, table_index: int = 0, limit: int = 50) -> dict:
    try:
        target: Path = resolve_path(filePath, must_exist=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc)}
    limit = max(1, min(int(limit or 50), 500))
    suffix = target.suffix.lower()

    if suffix in (".csv", ".tsv", ".txt"):
        return {"output": f"表格 {relative(target)}\n{_parse_delimited(target, limit)}"}

    if suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            return {"ok": False, "output": "未安装 openpyxl，无法读取 XLSX。请 `pip install openpyxl`（或先转成 CSV）"}
        wb = openpyxl.load_workbook(target, read_only=True, data_only=True)
        sheets = wb.sheetnames
        idx = max(0, min(int(table_index or 0), len(sheets) - 1))
        ws = wb[sheets[idx]]
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            rows.append("\t".join("" if v is None else str(v) for v in row))
            if i + 1 >= limit:
                break
        header = f"XLSX {relative(target)} | 工作表: {sheets}（显示 {sheets[idx]}）"
        return {"output": header + "\n" + "\n".join(rows)}

    return {"ok": False, "output": f"暂不支持的文件类型 {suffix}（支持 csv/tsv/xlsx）"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES"]
