"""符号计算与方程求解（sympy，需安装；未装时自动停用）。"""

from __future__ import annotations

import config

NAME = "symbolic_math"
DESCRIPTION = "符号计算与方程求解：化简、因式分解、求导、积分、解方程（需 sympy）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "description": "simplify=化简；factor=因式分解；derivative=求导；integrate=积分；solve=解方程；equals=等价判定",
            "enum": ["simplify", "factor", "derivative", "integrate", "solve", "equals"],
        },
        "expr": {"type": "string", "description": "表达式，如 `x**2 - 1`（sympy 语法）"},
        "variable": {"type": "string", "description": "变量名，如 `x`"},
        "expression2": {"type": "string", "description": "equals 用：第二个表达式"},
    },
    "required": ["operation", "expr"],
}

REQUIRES = ["pkg:sympy"]  # 未装 sympy 时自动停用；pip install sympy 后恢复


def _safe(s: str) -> str:
    import re
    s = (s or "").strip()
    # 只保留合法字符，防注入
    if re.search(r"[^0-9a-zA-Z_+\-*/^().,\s=<>]", s):
        raise ValueError(f"表达式含不支持的字符: {s!r}")
    return s.replace("^", "**")


def run(operation: str, expr: str, variable: str = "x", expression2: str = "") -> dict:
    try:
        import sympy
    except ImportError:
        return {"ok": False, "output": "未安装 sympy，无法符号计算。请 `pip install sympy`。"}

    op = (operation or "").lower()
    if not variable:
        variable = "x"
    sym = sympy.symbols(variable)
    try:
        e1 = sympy.sympify(_safe(expr))
        if op == "simplify":
            r = sympy.simplify(e1)
        elif op == "factor":
            r = sympy.factor(e1)
        elif op == "derivative":
            r = sympy.diff(e1, sym)
        elif op == "integrate":
            r = sympy.integrate(e1, sym)
        elif op == "equals":
            e2 = sympy.sympify(_safe(expression2))
            r = sympy.simplify(e1 - e2) == 0
            r = "等价" if r else "不等价"
        elif op == "solve":
            r = sympy.solve(e1, sym)
        else:
            return {"ok": False, "output": f"未知 operation: {operation}"}
        return {"output": f"{op}({expr}) = {r}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"符号计算失败: {exc}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES"]
