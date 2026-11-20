# notify_user — 向用户播报进度（人机边界）

## 作用
向用户发送一条进度/通知（不打断流程、不挂起）。适合长任务里的里程碑播报、状态更新。

## 参数
- `message`（string, 必填）：要展示给用户的简短通知。
- `level`（string, 可选）：info/progress/warning/done，默认 info。

## 返回
直接回显一条带标记的通知（`·`/`▶`/`⚠`/`✔`）。

## 注意事项
- 仅用于「播报」，不用于请求信息或决策；要提问用 `ask_followup_question`，要确认用 `confirm_action`。
