> [← 返回文档目录](../README.md)

# HTTP API（`app.py`）

FastAPI 后端路由。除页面路由外，`/api/*` 需先通过 `/api/auth/login` 登录。

## 认证与配置
| 方法 | 路径 |
|---|---|
| POST | `/api/auth/login` |
| POST | `/api/auth/logout` |
| GET | `/api/auth/status` |
| POST | `/api/auth/password` |
| GET / PUT | `/api/config` |
| POST | `/api/config/reload` |

## 模型与提供商
| 方法 | 路径 |
|---|---|
| GET / POST | `/api/providers` |
| DELETE | `/api/providers/{pid}` |
| POST | `/api/providers/{pid}/models` |
| POST | `/api/providers/{pid}/test` |
| POST | `/api/providers/{pid}/select` |
| GET | `/api/models` |

## 工具 / 技能 / MCP
| 方法 | 路径 |
|---|---|
| GET | `/api/tools` |
| POST | `/api/tools/refresh` |
| GET | `/api/tools/{name}/doc` |
| GET | `/api/skills` |
| GET | `/api/prompt` |
| GET | `/api/mcp` |
| POST | `/api/mcp/refresh` |
| POST | `/api/mcp/tools` |

## 文件 / 对话
| 方法 | 路径 |
|---|---|
| GET | `/api/files` |
| GET | `/api/file` |
| POST | `/api/chat` |
| POST | `/api/question/{qid}/answer` |
| GET / POST | `/api/conversations` |
| GET / PUT / DELETE | `/api/conversations/{cid}` |

## 系统与更新
| 方法 | 路径 |
|---|---|
| GET | `/api/health` |
| GET | `/api/update/status` |
| GET | `/api/update/result` |
| POST | `/api/update/apply` |

## 页面
`GET /`（登录与引导）、`GET /chat`、`GET /settings`。

> 以上路由均来自 `app.py` 的 `@app.*` 装饰器，前端 `web/js/*.js` 中有对应调用。
