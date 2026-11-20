# diff_compare — 文件/文本差异比较

## 作用
比较两个文件、或文件与给定文本之间的差异，输出 unified diff（增删行统计 + 上下文）。

## 参数
- `pathA`（string, 必填）：第一个文件（相对工作区）。
- `pathB`（string, 可选）：第二个文件；省略时用 `textB` 比较。
- `textA` / `textB`（string, 可选）：直接用文本代替文件内容。
- `context`（integer, 可选）：diff 上下文行数，默认 3。

## 返回
`差异：+N / -M` 及 unified diff（最多 1500 行）。

## 注意事项
- 比较同一文件在不同版本/分支的差异，配合 `git_ops`（`git diff`）。
- 工作区内不存在的路径会被沙箱拦截并报错。
