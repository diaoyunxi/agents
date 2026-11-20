# weather_query — 天气查询

## 作用
查询天气：按城市名（自动地理编码）或经纬度，取当前天气 + 未来 N 天预报。走 Open-Meteo 免密钥接口。

## 参数
- `location`（string, 可选）：城市名，如 `北京`、`London`。
- `latitude` / `longitude`（number, 可选）：给定则跳过城市解析。
- `forecast_days`（integer, 可选）：预报天数，默认 3，最大 7。
- `timeout`（integer, 可选）：默认 20 秒。

## 返回
`地点 / 当前(温度/体感/湿度/风速) / 每日(天气码/温度区间/降水概率)`。

## 注意事项
- 城市名解析不到时请给经纬度或换写法。
- 时效/突发天气建议结合 `news_search`。
