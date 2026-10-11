# computer_use — 无障碍树优先的桌面操控

## 作用

观察并操控 Windows 桌面窗口。核心思路参考开源项目 `a11y-computer-use`：**不去猜像素坐标**，
而是先抓取目标窗口「剪枝后的控件树」（每个控件带一个引用 `ref`，如 `e3`），再由你说
`click e3`。点击优先调用控件自身的无障碍动作（Invoke / Toggle / Select / Expand，不移动鼠标），
只有控件没有这些动作时才退化为坐标点击。文本输入优先用 `ValuePattern` 一步写值，否则聚焦后合成输入。

本工具仅支持 Windows（底层为系统自带的 UI Automation，通过 `comtypes` 调用，无需额外安装运行时）。

## 参数

- `action`（string, 必填）：动作，可选值：
  - `status`：检查当前环境是否可用。
  - `windows`：列出可见的顶层窗口（标题 / 进程 / 类名 / pid），用于确定 `app` 参数。
  - `snapshot`：抓取某个窗口的控件树，返回带 `ref` 的缩进文本。
  - `find`：在窗口里按条件筛选元素，只返回匹配项（快照过大时用它）。
  - `click`：点击元素（`ref`）或坐标（`x`/`y`）。
  - `type`：输入文本；给了 `ref` 会先把该元素聚焦。
  - `key`：发送快捷键组合。
  - `set_value`：用 `ValuePattern` 直接把元素的值设为 `value`。
  - `scroll`：滚动；`into_view=true` 时只把 `ref` 滚入可视区而不移动鼠标。
- `app`（string, 可选）：目标窗口，取标题 / 类名 / 进程名的**子串**（不区分大小写），如 `notepad.exe`。
- `ref`（string, 可选）：元素引用，形如 `e3`，来自最近一次 `snapshot` / `find`。
- `query`（string, 可选）：`find` 用，匹配标题或值的子串。
- `role`（string, 可选）：`find` 用，匹配角色子串，如 `button`、`edit`、`link`。
- `text`（string, 可选）：`type` 要输入的文本。
- `value`（string, 可选）：`set_value` 要写入的值。
- `chord`（string, 可选）：`key` 的快捷键，如 `ctrl+s`、`alt+f4`、`escape`。
- `x` / `y`（integer, 可选）：物理像素坐标，`click` / `scroll` 没有 `ref` 时使用。
- `button`（string, 可选）：鼠标键 `left` / `right` / `middle`，默认 `left`。
- `count`（integer, 可选）：点击次数 1-3，默认 1。
- `dx` / `dy`（integer, 可选）：`scroll` 的滚动格数，正数分别向右、向下。
- `into_view`（boolean, 可选）：`scroll` 用，只滚入可视区不移动鼠标。
- `max_elements`（integer, 可选）：`snapshot` 最多返回的元素数，默认 300。
- `include_bounds`（boolean, 可选）：是否在每行附带坐标矩形，默认否。

## 返回

根据动作返回纯文本。`snapshot` 形如：

```text
[snap-1] notepad.exe (window, 12 个元素)
  e1 window "无标题 - 记事本"
    e2 edit "文本编辑器" (edit)
    e3 button "文件" (click)
```

每行的格式为 `ref 角色 "标题" ="值" (标志)`；标志包含 `click`（可点击）、`edit`（可编辑）、
`focus`、`on`/`off`、`selected`、`expanded`/`collapsed`、`disabled`、`secure`（密码字段）、`offscreen`。

失败时返回 `{"ok": false, "output": "[错误码] 说明"}`，错误码与参考项目对齐，例如
`app_not_found`、`stale_ref`、`invalid_arguments`、`secure_field`、`focus_lost`、`unsupported`。

## 推荐用法

1. 先 `action=windows` 找到目标窗口，确定 `app` 子串。
2. `action=snapshot`（可先 `include_bounds=false` 省 token）拿到带 `ref` 的树。
3. 直接对 `ref` 操作：`click`、`type`、`set_value`、`key`、`scroll`。
4. 界面变化后重新 `snapshot`；报 `stale_ref` 说明旧 `ref` 已失效，重新观察再操作。

## 注意事项

- **ref 只在最近一次 `snapshot` / `find` 内有效**。执行动作时工具会在最新树上按
  「AutomationId → 角色+标题 → 就近位置」重新定位元素，定位不到会返回 `stale_ref`。
- 密码 / 安全字段不会被读取值，也不会被点击或输入，相关操作返回 `secure_field`。
- `snapshot` 的 `max_elements` 触发上限时会截断并给出提示，此时改用 `find` 更高效。
- 元素数量多时建议用 `find` 或 `role` 缩小范围，避免一次塞入过多 token。
- 本工具会真实操作用户桌面，属于高风险工具，可在设置页的「禁用列表」中关闭。
