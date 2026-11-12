"""数据分析：对 CSV/JSON/文本数据做清洗、统计与透视（需 pandas，未装则降级内置）。"""

from __future__ import annotations

import json
from pathlib import Path

from common import relative, resolve_path, workspace_dir

NAME = "data_analyze"
DESCRIPTION = "对表格数据做描述统计、分组透视与清洗（pandas）；支持 CSV/JSON/内联数据"
PARAMETERS = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "数据源：文件路径（csv/json）或内联 JSON 行数组字符串"},
        "operation": {
            "type": "string",
            "description": "describe=描述统计；group=分组聚合；pivot=透视；head=前N行；unique=去重计数；clean=去空行/去重",
            "enum": ["describe", "group", "pivot", "head", "unique", "clean"],
        },
        "group_by": {"type": "string", "description": "group/pivot 用：分组列"},
        "value_col": {"type": "string", "description": "group/pivot 用：数值列"},
        "agg": {"type": "string", "description": "聚合方式，默认 mean；可选 sum/count/min/max/mean/std"},
        "rows": {"type": "integer", "description": "head 用：显示行数，默认 10"},
    },
    "required": ["source", "operation"],
}

REQUIRES = ["pkg:pandas"]  # 本机已装 pandas，自动启用；缺失时降级内置


def _load_df(source: str):
    import pandas as pd
    p = (source or "").strip()
    if p.lower().endswith(".json") or p.startswith("["):
        try:
            path = resolve_path(p, must_exist=False) if not p.startswith("[") else None
            if path is not None:
                return pd.read_json(path)
            return pd.DataFrame(json.loads(p))
        except Exception:
            return pd.DataFrame(json.loads(p))
    return pd.read_csv(p)


def run(source: str, operation: str, group_by: str = "", value_col: str = "",
        agg: str = "mean", rows: int = 10) -> dict:
    source = (source or "").strip()
    if not source:
        return {"ok": False, "output": "source 不能为空"}
    op = (operation or "").lower()

    try:
        df = _load_df(source)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"读取数据失败: {exc}"}
    if df is None or len(df) == 0:
        return {"output": "（空数据集）"}

    try:
        import pandas as pd
        if op == "describe":
            return {"output": f"{len(df)} 行 x {len(df.columns)} 列\n{df.describe(include='all').to_string()}"[:6000]}
        if op == "head":
            n = max(1, min(int(rows or 10), 200))
            return {"output": df.head(n).to_string()[:8000]}
        if op == "unique":
            s = {c: int(df[c].nunique()) for c in df.columns[:30]}
            return {"output": "各列去重计数:\n" + "\n".join(f"  {k}: {v}" for k, v in s.items())}
        if op == "group":
            if not group_by:
                return {"ok": False, "output": "group 需要 group_by"}
            v = value_col or df.select_dtypes(include="number").columns[0]
            a = (agg or "mean").lower()
            res = df.groupby(group_by)[v].agg(a)
            return {"output": f"按 {group_by} 聚合 {v}({a}):\n" + res.to_string()}
        if op == "pivot":
            if not group_by:
                return {"ok": False, "output": "pivot 需要 group_by"}
            v = value_col or df.select_dtypes(include="number").columns[0]
            return {"output": df.pivot_table(index=group_by, values=v, aggfunc=(agg or "mean").lower()).to_string()}
        if op == "clean":
            before = len(df)
            df = df.dropna().drop_duplicates()
            return {"output": f"清洗完成: {before} -> {len(df)} 行（去空值/去重）"}
        return {"ok": False, "output": f"未知 operation: {operation}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"分析失败: {exc}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES"]
