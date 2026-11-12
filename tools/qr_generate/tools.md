# qr_generate — 生成/解析二维码

## 作用
- `action=generate`：把内容（URL/文本）编码成二维码并保存为 PNG 到工作区（需 `qrcode` 库，本机已装则自动启用）。
- `action=read`：从图片中解析二维码（需 `pyzbar`）。

## 参数
- `action`（string, 必填）：`generate` 或 `read`。
- `data`（string, generate 必填）：要编码的内容。
- `imagePath`（string, read 必填）：含二维码的图片路径。
- `outputPath`（string, 可选）：输出路径，默认 `qr_<时间戳>.png`。
- `size`（integer, 可选）：边长像素，默认 300。

## 门控
声明 `REQUIRES=["pkg:qrcode"]`：未安装 qrcode 时本工具自动停用；`pip install qrcode` 后自动恢复。

## 注意事项
- 生成的图片保存在工作区内，可用 `read_file` 查看。
