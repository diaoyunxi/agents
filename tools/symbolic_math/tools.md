# symbolic_math — 符号计算/方程求解

## 作用
用 sympy 做符号化简、因式分解、求导、积分、解方程、等价判定。表达式用 sympy 语法（如 `x**2 - 1`）。

## 参数
- `operation`（string, 必填）：`simplify`/`factor`/`derivative`/`integrate`/`solve`/`equals`。
- `expr`（string, 必填）：表达式。
- `variable`（string, 可选）：变量名，默认 `x`。
- `expression2`（string, 可选）：`equals` 用的第二个表达式。

## 门控
声明 `REQUIRES=["pkg:sympy"]`：未安装 sympy 时自动停用；`pip install sympy` 后自动恢复。

## 注意事项
- 数值计算/普通求值用 `calculator`（免依赖，总是可用）。
