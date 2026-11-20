# send_message — 团队消息通道

## 作用

在团队模式下与队友（其他代理/成员）通信：发送定向消息、广播，或回复协议类消息（关机请求、计划审批等）。当前项目未激活多代理团队时，消息会记录到本地会话日志并如实告知未送达。

## 参数

- `type`（string, 必填）：`message`（定向消息）/ `broadcast`（广播）/ `shutdown_request` / `shutdown_response` / `plan_approval_response`。
- `recipient`（string, 定向消息必填）：队友名称。
- `content`（string, 必填）：消息正文。
- `summary`（string, 可选）：一句话摘要（5-10 词）。

## 返回

发送结果：送达时给出队友待处理消息数；未注册队友时明确说明仅记录到本地日志。

## 注意事项

- 优先使用定向 `message`，避免不必要的 `broadcast`。
- 协议类消息（shutdown / plan_approval）须配合团队协作流程使用，不要滥用。
- 队友不在线时不要反复重发，先确认对方状态。
