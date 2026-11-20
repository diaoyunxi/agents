# academic_search — 学术论文/文献检索

## 作用
检索学术文献。默认走 arXiv API（免密钥，覆盖计算机、物理、数学、量化金融、生物等预印本）；`provider=pubmed` 走 PubMed 生物医学库。

## 参数
- `query`（string, 必填）：检索关键词。arXiv 支持布尔运算与限定符（如 `cat:cs.LG AND all:transformer`、`as:名字`）。
- `max_results`（integer, 可选）：默认 8，最大 25。
- `category`（string, 可选）：arXiv 学科分类（如 `cs.LG`、`stat.ML`），仅 arXiv 生效。
- `provider`（string, 可选）：`arxiv`（默认）或 `pubmed`。

## 返回
编号文献列表（标题 / 作者 / 链接 / 时间 / 摘要）。

## 注意事项
- 前沿技术、可复现模型与数据集优先查 arXiv；临床医学、生物医学优先 PubMed。
- 引用务必给出 DOI/链接与标题，避免凭记忆。
