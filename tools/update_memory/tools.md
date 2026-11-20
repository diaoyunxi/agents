# update_memory — 持久化记忆

## 作用

把跨会话有用的事实写入持久化记忆库（项目目录下 `.memory/knowledge.json`）：用户的稳定偏好、项目的关键决策与约定、反复用到的环境信息。更新或删除时必须带上既有记忆的 ID。

## 参数

- `action`（string, 必填）：`create` / `update` / `delete`。
- `title`（string, 可选）：简短标题。
- `knowledge_to_store`（string, create/update 必填）：要记住的具体内容，一段话以内。
- `existing_knowledge_id`（string, update/delete 必填）：既有记忆的 ID（每次调用后返回的清单里可以看到）。

## 返回

操作结果 + 当前记忆库全量清单（含 ID、标题、更新时间）。

## 注意事项

- 只存**跨会话仍有价值**的信息；一次性的任务细节不要存。
- 发现某条记忆过时或错误时，用 `update` 覆盖或 `delete` 删除，不要堆叠重复记忆。
- 内容一段话以内，写清楚「是什么 + 为什么 + 关键细节」。
