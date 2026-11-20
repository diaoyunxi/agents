# confirm_action — 不可逆操作二次确认（治理）

## 作用
对不可逆操作做二次确认：向用户展示操作要点，挂起等待「确认执行/取消」。拒绝时不得继续。比 `request_approval` 更轻量，适合删除、覆盖、发布等一步确认场景。

## 参数
- `message`（string, 必填）：要确认的操作说明（含将产生的影响）。
- `confirm_label`（string, 可选）：确认按钮文案，默认「确认执行」。
- `timeout`（integer, 可选）：等待秒数，默认 300。

## 返回
发起确认并挂起；用户选择后回灌为文本。

## 适用
`file_delete`、`write_to_file` 覆盖已有文件、`git_ops` 的 reset/force-push 等不可逆动作前调用。
