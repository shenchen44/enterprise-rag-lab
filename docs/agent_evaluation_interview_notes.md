# 企业财报 RAG：Agent 评测与检索功能说明

本项目面向企业财报问答，提供从 PDF 入库、混合检索、生成回答到离线评测的完整 RAG 工作流。评测设计将问题拆为 ingestion、retrieval 和 generation 三层，便于定位问题发生的位置。

## 1. 评测数据

评测样本使用以下字段：

```json
{
  "question": "问题",
  "expected_sources": ["正确 PDF"],
  "expected_pages": ["正确证据页"],
  "reference_answer": "标准答案",
  "reference_justification": "参考理由（可选）"
}
```

`expected_sources` 和 `expected_pages` 用于评估检索是否找到正确来源及证据页；`reference_answer` 用于评估生成回答。页码比较兼容评测集的 0-based 页码与 PDF 解析器的 1-based 页码。

## 2. Ingestion / Chunking Integrity

实现：[`src/eval/retrieval_metrics.py`](../src/eval/retrieval_metrics.py)

该层只验证数据是否完整进入索引、chunk 是否可追溯，不将长度或字符串匹配误称为语义切分质量。

| 指标 | 计算方法 | 用途 |
| --- | --- | --- |
| Indexed chunks | 已入库的 chunk 总数 | 记录索引规模。 |
| Source chunk coverage | 正确 PDF 至少有一个 chunk 的题数 / 全部题数 | 排查正确 PDF 是否整体未入库。 |
| Evidence-page chunk coverage | 每题被 chunk 覆盖的正确证据页数 / 标注证据页数，再取均值 | 验证关键证据页没有在解析、切分或入库时丢失。 |
| Page metadata coverage | 带可解析页码的 chunk 数 / 全部 chunk 数 | 保证检索结果能引用回 PDF 页。 |
| Average / Median / P90 chunk chars | 全部 chunk 字符长度的平均数、中位数、90 分位数 | 观察常规切分粒度与超长 chunk 尾部。 |
| Empty chunk ratio | 空文本 chunk 数 / 全部 chunk 数 | 排查空页或解析残留。 |

`Source chunk coverage` 和 `Evidence-page chunk coverage` 的粒度不同：前者只检查正确 PDF 是否进入索引，后者检查该 PDF 中标注的正确页面是否被覆盖。后者为主指标，前者用于定位文件级入库问题。

## 3. Retrieval Effectiveness

实现：[`src/eval/retrieval_metrics.py`](../src/eval/retrieval_metrics.py)、[`src/eval/run_eval.py`](../src/eval/run_eval.py)

| 指标 | 计算方法 | 用途 |
| --- | --- | --- |
| Source Hit Rate | Top-K 出现正确 PDF 的题数 / 总题数 | 是否找到了正确文件。 |
| Source MRR | 每题 `1 / 正确 PDF 首次排名` 的平均值；未命中为 0 | 正确文件是否排在前面。 |
| Page Hit Rate | Top-K 出现正确 PDF 且正确证据页的题数 / 总题数 | 是否找到了至少一个正确证据页。 |
| Page MRR | 每题 `1 / 正确证据页首次排名` 的平均值 | 正确证据页是否排在前面。 |
| Expected-page Recall | 每题命中的正确页数 / 标注正确页数，再取均值 | 多页答案所需证据是否找全。 |
| Retrieved Reference-term Recall | Top-K 文本命中的参考关键词/数值数 / 参考词总数 | 用于诊断缺失的答案线索。 |
| Retrieval latency | 单题检索耗时与平均耗时 | 观察质量与响应性能的关系。 |

Reference-term Recall 仅用于诊断：它是归一化字符串匹配，不能替代基于 evidence span 或 claim 的检索评测。

## 4. Generation Quality

实现：[`src/eval/run_ragas_eval.py`](../src/eval/run_ragas_eval.py)

端到端评测会保存每题的检索上下文、生成答案、citation、检索指标、检索耗时和生成耗时，并使用 RAGAS 计算：

| 指标 | 计算方法 | 用途 |
| --- | --- | --- |
| Faithfulness | 能由 retrieved contexts 支持的回答原子陈述数 / 回答原子陈述总数 | 判断回答是否有上下文依据。 |
| Answer Relevancy | 从回答反向生成问题，与原问题计算 embedding cosine similarity；回避式答案记为 0 | 判断回答是否聚焦于用户问题。 |
| Answer Correctness | `0.75 × Statement F1 + 0.25 × Semantic Similarity` | 判断回答与 reference 的事实覆盖和整体语义一致性。 |

Statement F1 使用回答和 reference 的原子陈述分类结果：

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × Precision × Recall / (Precision + Recall)
```

## 5. 检索与证据增强功能

### Hybrid retrieval

[`src/retrieval/hybrid.py`](../src/retrieval/hybrid.py) 融合向量检索和 BM25，并支持 reranker。RRF 用于合并多路候选结果。

### 财报查询扩展

[`src/retrieval/query_expansion.py`](../src/retrieval/query_expansion.py) 为财务问题提供领域相关的查询扩展，用于缓解业务问题表述与财报字段名称不一致的问题。端到端评测路径避免重复扩展同一问题。

### 页面级检索

[`src/retrieval/page_retriever.py`](../src/retrieval/page_retriever.py) 建立页面级向量与 BM25 检索，并将页面证据补充到常规 chunk 检索结果中，保留跨 chunk 的表格与段落上下文。

### 表格行检索与页码元数据

[`src/ingestion/docling_tables.py`](../src/ingestion/docling_tables.py) 将 Docling 表格和表格行关联到 PDF 页码；[`src/retrieval/hybrid.py`](../src/retrieval/hybrid.py) 会对财务数值、比率、收入、资产负债等问题补充表格行证据，并限制候选来源于已经召回的文件。

迁移脚本：[`scripts/migrate_table_page_metadata.py`](../scripts/migrate_table_page_metadata.py)。

### Source-focused sweep

Hybrid Retriever 可在初步命中的候选 PDF 内部重扫 chunks，利用查询词项、数值和表格字段寻找补充证据。该功能通过 `SOURCE_SWEEP_ENABLED` 配置开关控制。

### 可引用的财务计算辅助

[`src/retrieval/financial_calculator.py`](../src/retrieval/financial_calculator.py) 从表格文本提取行项目，并向生成上下文追加带 citation 的确定性计算证据，支持：

- Quick ratio
- Largest liability
- Effective tax rate

数值解析支持财报常见的括号负数格式，例如 `(0.6)%`。

## 6. 评测运行与恢复

RAGAS 评测支持 batch、checkpoint 和 resume。运行中断后，可以从 checkpoint 恢复已完成样本；每题同时保留 citation 和阶段性耗时，便于追踪和复盘。

```bash
# 独立检索与入库完整性评测
uv run python -m src.eval.run_eval \
  --questions eval/financebench_questions.jsonl \
  --output reports/rag_eval_report.md \
  --json-output reports/rag_eval_report.json

# 端到端 RAGAS 评测
uv run python -m src.eval.run_ragas_eval \
  --questions eval/financebench_questions.jsonl \
  --output reports/ragas_eval_report.md \
  --json-output reports/ragas_eval_report.json

# 测试
uv run pytest
```

## 7. 相关测试

| 测试 | 覆盖内容 |
| --- | --- |
| [`tests/test_retrieval_metrics.py`](../tests/test_retrieval_metrics.py) | 来源、页码、检索指标与入库完整性指标。 |
| [`tests/test_hybrid_retrieval.py`](../tests/test_hybrid_retrieval.py) | 混合检索、查询扩展、页面与表格候选合并。 |
| [`tests/test_page_retriever.py`](../tests/test_page_retriever.py) | 页面级 BM25 与向量融合。 |
| [`tests/test_docling_tables.py`](../tests/test_docling_tables.py) | 表格与页码元数据提取。 |
| [`tests/test_financial_calculator.py`](../tests/test_financial_calculator.py) | 财务行项目、负数解析与确定性计算辅助。 |
