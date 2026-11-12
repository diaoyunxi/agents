# request_approval — 高风险操作人工审批（治理）

## 作用
对高风险操作发起人工审批门控：向用户说明拟执行动作与风险级别，挂起等待用户「批准/拒绝」。复用交互式选择机制，未获批准不得执行该操作。

## 参数
- `action`（string, 必填）：拟执行的高风险动作完整描述（改什么、影响什么、是否可回滚）。
- `risk`（string, 可选）：low/medium/high/critical，默认 high。
- `context`（string, 可选）：帮助判断的补充背景。
- `timeout`（integer, 可选）：等待秒数，默认 300，最大 3600。

## 返回
发起审批并挂起；用户选择后回灌为文本。

## 适用
`database_write`、`email_send`、`payment_execute`、`cloud_deploy`、`docker_manage`、`git_ops` 写操作等高风险工具执行前调用。
