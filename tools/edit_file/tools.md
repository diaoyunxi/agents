# edit_file — 精确编辑文件

## 作用

在已有文件上做小范围修改，支持四种模式：查找替换、在文件尾部/头部插入文本、按行号删除。
每次修改都会在右侧「文件变更」面板生成 diff 记录。相比 `write_file` 整体覆盖，优先使用本工具改动已有文件。

## 参数

- `path`（string, 必填）：目标文件的相对路径，必须已存在。
- `mode`（string, 可选）：`replace`（默认）、`append`、`prepend`、`delete_lines`。
- `old_string`（string, `replace` 必填）：要被替换的原文，必须与文件内容完全一致（含缩进）。
- `new_string`（string, 可选）：替换后的新文本；留空或省略表示删除这段内容。
- `replace_all`（boolean, 可选）：是否替换全部出现的位置，默认 `false`（只替换第一处）。
- `content`（string, `append` / `prepend` 使用）：要插入的文本；省略时回退使用 `new_string`。
- `start_line` / `end_line`（integer, `delete_lines` 使用）：删除的行号区间，含首含尾，从 1 开始。

## 返回

`已编辑 src/app.py（replace，影响 1 处）`；若未找到原文，会返回最接近的行号提示。

## 注意事项

- `old_string` 必须是精确片段；上下文太长容易失配，建议包含 1~3 行唯一上下文。
- 单次编辑建议不超过 50 行，超过请拆成多次调用。
- 修改前不确定现状时，先 `read_file` 确认。
