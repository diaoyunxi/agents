# chart_generate — 生成图表

## 作用
把数据画成折线/柱状/散点/饼图，保存为 PNG 到工作区（matplotlib，需安装）。

## 参数
- `chart_type`（string, 必填）：`line`/`bar`/`scatter`/`pie`。
- `data`（string, 必填）：JSON 字符串。折线/柱状/散点用 `{"x":[...],"y":[...]}`；饼图用 `{"labels":[...],"values":[...]}`。
- `outputPath`（string, 可选）：默认 `chart.png`。
- `title`（string, 可选）：图标题。

## 门控
声明 `REQUIRES=["pkg:matplotlib"]`：未安装时自动停用；`pip install matplotlib` 后恢复。

## 配合
- 数据先用 `data_analyze` 清洗/聚合，再画图；图片用 `read_file` 查看。
