"""生成图表并保存为图片（matplotlib，未装则自动停用；可用 python_execute 代替）。"""

from __future__ import annotations

import json
from pathlib import Path

from common import record_change, relative, resolve_path, workspace_dir

NAME = "chart_generate"
DESCRIPTION = "用数据生成折线/柱状/散点/饼图并保存为 PNG（需 matplotlib）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "chart_type": {"type": "string", "description": "line/bar/scatter/pie", "enum": ["line", "bar", "scatter", "pie"]},
        "data": {"type": "string", "description": "数据：JSON 字符串，如 {\"x\":[...],\"y\":[...]} 或 {\"labels\":[...],\"values\":[...]}"},
        "outputPath": {"type": "string", "description": "输出文件路径（相对工作区），默认 chart.png"},
        "title": {"type": "string", "description": "图表标题，可选"},
    },
    "required": ["chart_type", "data"],
}

REQUIRES = ["pkg:matplotlib"]  # 未装 matplotlib 时自动停用


def run(chart_type: str, data: str, outputPath: str = "chart.png", title: str = "") -> dict:
    ctype = (chart_type or "").lower()
    if ctype not in ("line", "bar", "scatter", "pie"):
        return {"ok": False, "output": "chart_type 需为 line/bar/scatter/pie"}
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "output": f"data 需为合法 JSON: {exc}"}

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"ok": False, "output": "未安装 matplotlib，无法生成图表。请 `pip install matplotlib`（或用 python_execute 写脚本生成）"}

    try:
        fig, ax = plt.subplots(figsize=(8, 5))
        if ctype == "pie":
            labels = parsed.get("labels") or [f"p{i}" for i in range(len(parsed.get("values", [])))]
            values = parsed.get("values") or []
            ax.pie(values, labels=labels, autopct="%1.0f%%")
        else:
            x = parsed.get("x", list(range(1, len(parsed.get("y", [])) + 1)))
            y = parsed.get("y") or []
            if ctype == "line":
                ax.plot(x, y, marker="o")
            elif ctype == "bar":
                ax.bar(range(len(y)), y)
            else:
                ax.scatter(x, y)
        if title:
            ax.set_title(title)
        fig.tight_layout()

        out_rel = outputPath or "chart.png"
        target: Path = resolve_path(out_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(target, dpi=100)
        record_change(target, "create")
        return {"output": f"已生成 {ctype} 图 {relative(target)}（可用 read_file 查看）"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"生成图表失败: {exc}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES"]
