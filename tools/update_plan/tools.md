# update_plan — 更新任务计划（编排）

## 作用
更新 `create_plan` 生成的计划：置步骤状态（pending/in_progress/done/skipped）、追加步骤、加进度备注；落盘并回显最新计划。

## 参数
- `plan_id`（string, 必填）：`create_plan` 返回的计划 ID。
- `step_index`（integer, 可选）：要置状态的步骤序号（0 起），配合 `status`。
- `status`（string, 可选）：`pending`/`in_progress`/`done`/`skipped`。
- `add_step`（string, 可选）：追加一个新步骤。
- `note`（string, 可选）：追加一条进度备注。

## 返回
更新后的完整计划渲染。

## 适用
边做边更新：完成一步就置 `done`，开始下一步置 `in_progress`，保持计划与实际进度一致。
