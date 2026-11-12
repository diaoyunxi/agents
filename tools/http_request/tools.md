# http_request — 发起 HTTP 请求

## 作用
对任意 http(s) 端点发起请求（自定义方法、请求头、请求体、query 参数），返回状态码、关键响应头与响应体（自动美化 JSON、截断大响应）。适合调用 REST API、Webhook 与只读接口。

## 参数
- `url`（string, 必填）：完整 URL。
- `method`（string, 可选）：GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS，默认 GET。
- `headers`（object, 可选）：自定义请求头。
- `body`（string, 可选）：原始请求体（JSON 请传序列化好的字符串）。
- `params`（object, 可选）：query 参数。
- `timeout`（integer, 可选）：默认 30，最大 120。
- `max_chars`（integer, 可选）：响应体最多返回字符数，默认 8000。

## 返回
方法+URL、`HTTP 状态码 | 字节数`、关键头、`--- body ---` 正文。

## 注意事项
- 写操作（POST/PUT/DELETE 修改远端状态）请确认影响；极高风险的对外写操作应先 `request_approval`。
- 网页正文提取请用 `web_fetch`；纯 API 调用用本工具更直接。
