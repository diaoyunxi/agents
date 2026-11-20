# calculator — 数学计算

## 作用
安全求值数学表达式（用 AST 白名单，不使用 `eval`，无任意代码执行风险）。支持四则、幂、取模、内置三角/对数/阶乘函数与常量。

## 参数
- `expression`（string, 必填）：表达式，如 `2**10 + sqrt(144)`、`factorial(5)`、`log10(1000)`。
- `variables`（object, 可选）：变量字典，如 `{"x": 3, "y": 2}`，表达式可直接引用。

## 可用符号
- 常量：`pi`、`e`、`tau`、`inf`、`nan`
- 函数：`sqrt abs round pow min max sin cos tan asin acos atan atan2 log log10 log2 exp factorial floor ceil fmod cbrt deg rad`

## 注意事项
- 结果为整值时以整数显示；需要精确小数可用 `round(x, n)`。
- 复杂符号推导/方程求解请用 `symbolic_math`（需安装 `sympy`）。
