# audit_log — 工具调用审计（治理）

## 作用
把一次工具调用/决策追加记入工作区审计日志（`.audit/audit.jsonl`），用于事后追溯、合规与高风险操作留痕。

## 参数
- `tool`（string, 必填）：被审计的工具名。
- `input_summary`（string, 可选）：输入摘要（避免记录敏感明文，可脱敏）。
- `output_summary`（string, 可选）：输出摘要。
- `decision`（string, 可选）：决策说明（为何批准/拒绝/放行）。
- `risk`（string, 可选）：low/medium/high/critical，默认 low。

## 返回
`已记录审计: 工具名（risk=…）-> audit.jsonl`。

## 适用
与 `request_approval` / `confirm_action` 配套：高风险操作前/后各记一条，保证可追溯。
