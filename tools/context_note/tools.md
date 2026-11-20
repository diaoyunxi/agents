# context_note — 上下文沉淀（元认知）

## 作用
把长任务中的关键事实、决策、中间状态追加到工作区 `.context/notes.md`，供后续轮次跨会话引用，对抗「上下文遗忘/腐烂」。

## 参数
- `fact`（string, 必填）：要记住的关键事实/决策/结论。
- `category`（string, 可选）：分类标签，如 `decision`/`fact`/`state`/`open_issue`。
- `review`（boolean, 可选）：为 `true` 时只回读当前已沉淀内容，不写入。

## 返回
已沉淀条数；或 `review=true` 时回读全部沉淀。

## 适用
多步骤任务中，把「已确认的结论」「已做的选择」「未决问题」持续落盘，避免重复推导或遗忘前提。
