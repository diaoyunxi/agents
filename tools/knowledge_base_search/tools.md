# knowledge_base_search — 本地知识库检索（RAG/关键词）

## 作用
对本地知识库做关键词检索与写入。数据存于工作区 `.kb/kb.sqlite`（SQLite，免外部向量库；后续可升级为 FTS/向量）。

## 参数
- `action`（string, 必填）：`add`（写入）/`search`（检索）/`list`（列出）/`delete`（删除）。
- `query`（string, search 必填）：关键词（空格分词，中英文都支持）。
- `title` / `content`（string, add 用）：条目标题与正文。
- `tags`（string, add 用）：逗号分隔标签。
- `id`（string, delete 用）：要删除的条目 ID。
- `limit`（integer, 可选）：最多返回条数，默认 10。

## 返回
按相关度排序的条目（ID/标题/正文节选/标签）。

## 注意事项
- 这是关键词检索，不是语义向量检索；需要向量检索时配 `pkg:chromadb`/`pkg:faiss` 后另建工具。
- 跨会话保留，存于工作区内。
