# javascript_execute — 执行 JS/Node 代码

## 作用
执行一段 JavaScript（CommonJS）：写入工作区临时 .js，用本机 `node` 运行，回显 exit_code/stdout/stderr。

## 参数
- `code`（string, 必填）：JS 源码。
- `timeout`（integer, 可选）：默认 30 秒，最大 300 秒。
- `stdin`（string, 可选）：写入标准输入。

## 门控
声明 `REQUIRES=["cli:node"]`：本机未装 Node.js 时自动停用；安装后自动恢复。

## 注意事项
- `DANGEROUS`：可执行任意 JS；有副作用的脚本先确认。
