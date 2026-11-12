"""计算器：安全的数学表达式求值（标准库，无 eval 风险）。"""

from __future__ import annotations

import ast
import math
import operator

NAME = "calculator"
DESCRIPTION = "安全计算数学表达式（四则、幂、取模、三角/对数/阶乘、常量与变量），返回结果"
PARAMETERS = {
    "type": "object",
    "properties": {
        "expression": {"type": "string", "description": "要计算的表达式，如 2**10 + math.sqrt(144) 或 factorial(5)"},
        "variables": {
            "type": "object",
            "description": "可选的变量字典，如 {\"x\": 3, \"y\": 2}，表达式中可直接引用",
        },
    },
    "required": ["expression"],
}

_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "pow": pow, "min": min, "max": max,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "atan2": math.atan2, "log": math.log, "log10": math.log10,
    "log2": math.log2, "exp": math.exp, "factorial": math.factorial,
    "floor": math.floor, "ceil": math.ceil, "fmod": math.fmod, "cbrt": lambda x: x ** (1 / 3),
    "deg": math.degrees, "rad": math.radians,
}
_ALLOWED_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf, "nan": math.nan}


class _Eval:
    def __init__(self, names: dict):
        self.names = names

    def visit(self, node):
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量: {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in self.names:
                return self.names[node.id]
            raise ValueError(f"未知变量: {node.id}")
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](self.visit(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Name) or func.id not in _ALLOWED_FUNCS:
                raise ValueError(f"仅允许内置数学函数，禁用: {getattr(func, 'id', func)}")
            args = [self.visit(a) for a in node.args]
            for kw in node.keywords:
                raise ValueError("不支持关键字参数")
            return _ALLOWED_FUNCS[func.id](*args)
        if isinstance(node, (ast.Tuple, ast.List)):
            return [self.visit(e) for e in node.elts]
        raise ValueError(f"不支持的语法: {type(node).__name__}")


def run(expression: str, variables: dict | None = None) -> dict:
    expr = (expression or "").strip()
    if not expr:
        return {"ok": False, "output": "expression 不能为空"}

    names = {k: v for k, v in _ALLOWED_CONSTS.items()}
    if variables:
        for k, v in variables.items():
            if not isinstance(v, (int, float)):
                return {"ok": False, "output": f"变量 {k} 必须是数字，收到 {v!r}"}
            names[k] = v

    try:
        tree = ast.parse(expr, mode="eval")
        result = _Eval(names).visit(tree)
        if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
            result = int(result)
        return {"output": f"{expr} = {result}"}
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, NameError) as exc:
        return {"ok": False, "output": f"计算失败: {exc}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
