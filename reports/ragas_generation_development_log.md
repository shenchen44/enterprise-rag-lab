# RAGAS Generation Evaluation Development Log

本文档记录从开始做 RAG 生成阶段评测，到完成 FinanceBench 46 题全量 RAGAS 测试期间的关键问题、修改原因、实现方案和指标变化。

## 1. 背景

项目最初已经完成了检索阶段建设：

- 使用 Chroma 作为持久化向量数据库。
- 使用 FastEmbed + `BAAI/bge-small-en-v1.5` 做 embedding。
- 使用 BM25 + Vector Search + RRF 做 Hybrid Retrieval。
- 使用 `BAAI/bge-reranker-base` 做 cross-encoder rerank。
- FinanceBench 子集扩展到 46 个问题，10 份财报文档，约 5190 个 chunks。

检索阶段效果已经比较好，因此后续重点转向 **生成阶段评测**：

- 生成回答是否忠实于检索证据。
- 回答是否和问题相关。
- 回答是否接近标准答案。
- 全量评测是否能稳定跑完。

对应评测指标采用 RAGAS：

- `faithfulness`
- `answer_relevancy`
- `answer_correctness`

## 2. 初始 RAGAS 接入问题

### 问题

最开始实现 `src/eval/run_ragas_eval.py` 后，遇到几个工程兼容性问题：

1. RAGAS 和 LangChain 版本之间存在 deprecated warning。
2. DeepSeek OpenAI-compatible API 不支持 `n > 1`，而 RAGAS 内部可能会请求多 completion。
3. 生成评测比检索评测慢很多，容易因为 API timeout 或中途中断导致整轮实验作废。

### 修改

在 `src/eval/run_ragas_eval.py` 中使用：

```python
LangchainLLMWrapper(..., bypass_n=True)
```

这样 RAGAS 内部如果需要多次 completion，会转成多次单 completion 调用，避免 DeepSeek API 报错。

### 结果

RAGAS smoke test 可以正常跑通，说明 DeepSeek + RAGAS 链路可用。

第一条 smoke test 指标：

| Total | Faithfulness | Answer Relevancy | Answer Correctness |
|---:|---:|---:|---:|
| 1 | 0.750 | 0.000 | 0.424 |

当时暴露出的主要问题是：模型经常回答 `insufficient information`，即使检索结果里有部分可用证据。

## 3. Baseline 生成评测

### 配置

初始生成 prompt 较保守：

- 只能使用 retrieved evidence。
- 如果证据不足就拒答。
- 每个事实需要 citation。

### 结果

5 题 baseline：

| Total | Faithfulness | Answer Relevancy | Answer Correctness | Avg Time |
|---:|---:|---:|---:|---:|
| 5 | 0.814 | 0.199 | 0.359 | 114.6s |

报告文件：

- `reports/ragas_eval_5.md`
- `reports/ragas_eval_5.json`

### 分析

这个结果说明：

- `faithfulness` 较高，说明模型比较保守，不太胡编。
- `answer_correctness` 较低，说明回答和标准答案差距大。
- `answer_relevancy` 很低，说明很多回答是“证据不足”，没有真正回答问题。

FinanceBench 的问题经常不是简单信息抽取，而是需要：

- 从财报中找到多个 line items。
- 做简单公式计算。
- 判断指标是否有意义。

如果 prompt 只强调“证据不足就拒答”，模型会过度保守。

## 4. 修改一：生成 Prompt 从保守 QA 改为财务分析模式

### 修改原因

Baseline 的主要失败模式是：

- 检索结果中有部分证据。
- 但最终指标没有直接写出来。
- 模型不敢用已有 line items 做简单计算。
- 最后回答 `insufficient information`。

因此 prompt 需要明确告诉模型：

- 先识别公司、期间、指标和数字字段。
- 如果最终指标没有直接给出，但所需 line items 存在，可以做简单计算。
- 不要因为最终比例没有直接出现就拒答。
- 每个数字和事实都必须带 citation。

### 实现位置

`src/eval/run_ragas_eval.py`

核心改动：

- 重写 `GENERATION_PROMPT`。
- 增加 `--generation-top-k`，评测时可以临时扩大生成上下文数量，不需要修改 `.env`。

### 结果

5 题结果：

| Version | Faithfulness | Answer Relevancy | Answer Correctness |
|---|---:|---:|---:|
| Baseline | 0.814 | 0.199 | 0.359 |
| Prompt v2 + top_k=8 | 0.678 | 0.199 | 0.413 |

报告文件：

- `reports/ragas_eval_5_prompt_v2.md`
- `reports/ragas_eval_5_prompt_v2.json`

### 分析

改 prompt 后：

- `answer_correctness` 从 0.359 提升到 0.413。
- 说明模型开始更愿意尝试财务分析和计算。
- 但 `faithfulness` 从 0.814 下降到 0.678。

这说明单纯放宽 prompt 有副作用：

- 模型更积极回答了。
- 但如果证据本身没有召回关键表格，模型可能会产生证据外推断。

因此下一步不能只继续调 prompt，而要提升生成阶段拿到的证据质量。

## 5. 修改二：Finance Query Expansion

### 修改原因

FinanceBench 很多问题的表述和财报中的字段名不完全一致。

例如：

- 用户问 `capital-intensive`，财报里可能是 `capital expenditures`、`property, plant and equipment`、`total assets`。
- 用户问 `quick ratio`，财报里是 `current assets`、`inventories`、`current liabilities`。
- 用户问 `EBITDA less capex`，财报里是 `operating profit`、`depreciation and amortization`、`capital spending`。

如果只用原问题检索，很容易召回管理层讨论段落，而不是财务表格 line items。

### 实现

在 `src/eval/run_ragas_eval.py` 中加入财务字段扩展词表：

```python
FINANCE_EXPANSION_TERMS = {
    "quick ratio": "current assets inventories inventory current liabilities cash receivables short term investments",
    "ebitda": "operating income operating profit depreciation amortization capital expenditures capital spending net revenue",
    ...
}
```

实现流程：

1. 根据问题触发关键词扩展。
2. 对原问题和扩展问题分别检索。
3. 使用 RRF 融合多路检索结果。
4. 再使用 reranker 做最终排序。

### 结果

5 题结果：

| Version | Faithfulness | Answer Relevancy | Answer Correctness |
|---|---:|---:|---:|
| Baseline | 0.814 | 0.199 | 0.359 |
| Prompt v2 + top_k=8 | 0.678 | 0.199 | 0.413 |
| Prompt v2 + Query Expansion + top_k=8 | 0.773 | 0.358 | 0.494 |

报告文件：

- `reports/ragas_eval_5_prompt_query_expansion.md`
- `reports/ragas_eval_5_prompt_query_expansion.json`

### 分析

Query Expansion 带来明显收益：

- `answer_correctness` 从 0.359 提升到 0.494。
- `answer_relevancy` 从 0.199 提升到 0.358。
- `faithfulness` 比只改 prompt 更高，从 0.678 回升到 0.773。

说明问题核心不只是 prompt，而是：

> 生成模型必须拿到足够接近财务 line items 的证据，才可能正确回答需要计算的问题。

其中 Q2 和 Q5 改善最明显：

- Q2 operating margin change 的 correctness 从 0.202 提升到 0.756。
- Q5 debt securities 的 correctness 从 0.727 提升到 0.977。

## 6. 修改三：Neighbor Chunk Augmentation

### 修改原因

财报 PDF 经过 chunking 后，一个完整表格可能被切到多个 chunk 中。

例如：

- 当前 chunk 命中了表头。
- 上一个 chunk 有年份。
- 下一个 chunk 有具体数值。

如果只把命中的 chunk 给模型，模型仍然可能缺少计算所需数字。

### 实现

在 `src/eval/run_ragas_eval.py` 中实现：

- `build_neighbor_lookup`
- `augment_with_neighbor_chunks`

逻辑：

1. 根据 `source_path + chunk_index` 建立 chunk 邻接索引。
2. 对命中 chunk 取前后相邻 chunk。
3. 把相邻 chunk 放入候选集。
4. 再交给 reranker 重新排序。

CLI 参数：

```bash
--neighbor-window 1
```

### 实验结论

Neighbor Chunk Augmentation 对表格问题有理论价值，但全量跑时输入上下文会变长，DeepSeek 生成阶段耗时明显上升。

因此在全量稳定测试中采用了：

```bash
--neighbor-window 0
```

也就是保留能力，但全量主结果先使用更稳定配置。

后续可以单独做 ablation：

- `neighbor-window=0`
- `neighbor-window=1`
- `neighbor-window=2`

比较对表格计算题的影响。

## 7. 修改四：Context Compression

### 修改原因

全量生成评测时，如果把多个长 chunk 直接塞给模型，会带来几个问题：

- token 成本高。
- 单题响应慢。
- 更容易 timeout。
- 模型更容易被无关段落干扰。

### 实现

在 `src/eval/run_ragas_eval.py` 中实现：

- `compress_context_text`
- `compress_hits_for_generation`

压缩策略：

1. 将 chunk 按句子或换行切分。
2. 根据问题词 overlap 打分。
3. 对包含数字的句子加分。
4. 对包含财务关键词的句子加分。
5. 保留最相关的若干句。

CLI 参数：

```bash
--disable-context-compression
```

默认启用 context compression。

### 结果

Context Compression 的核心收益不是单独提高指标，而是提升全量评测稳定性：

- 降低输入长度。
- 提升生成速度。
- 降低中途卡死概率。

## 8. 修改五：全量评测工程化

### 问题

RAGAS 全量评测非常慢：

- 每道题先生成答案。
- 每道题再跑 3 个 RAGAS 指标。
- 每个指标又可能调用 LLM。

如果中途失败，整轮实验会浪费大量时间。

### 修改

增加以下能力：

#### 1. 分批评测

CLI 参数：

```bash
--ragas-batch-size 5
```

每 5 题跑一个 RAGAS batch。

#### 2. Checkpoint

CLI 参数：

```bash
--checkpoint-output reports/ragas_eval_full_stable_checkpoint.json
```

checkpoint 写入两个阶段：

- 生成阶段：每生成 5 题写一次。
- RAGAS 阶段：每完成一个 batch 写一次。

#### 3. Resume

CLI 参数：

```bash
--resume
```

如果 checkpoint 中已有：

- `generated_answer`
- `retrieved_contexts`
- RAGAS scores

则自动复用，不重复调用模型。

### 验证

做了 resume smoke test：

第一次运行生成并打分 2 题。

第二次使用 `--resume` 后输出：

```text
Running RAGAS evaluation on 0 samples
```

说明已完成的样本不会重复计算。

报告文件：

- `reports/ragas_eval_resume_smoke.md`
- `reports/ragas_eval_resume_smoke_2.md`
- `reports/ragas_eval_resume_smoke_checkpoint.json`

## 9. 全量稳定测试

### 命令

最终全量稳定测试命令：

```bash
uv run python -m src.eval.run_ragas_eval \
  --questions eval/financebench_questions.jsonl \
  --generation-top-k 6 \
  --neighbor-window 0 \
  --ragas-batch-size 5 \
  --checkpoint-output reports/ragas_eval_full_stable_checkpoint.json \
  --output reports/ragas_eval_full_stable.md \
  --json-output reports/ragas_eval_full_stable.json
```

### 为什么使用这个配置

使用 `generation-top-k=6`：

- 比默认 `top_k=5` 多一些证据。
- 比 `top_k=8` 更稳定、更快。

使用 `neighbor-window=0`：

- Neighbor chunk 对表格问题有潜力。
- 但在全量评测中会显著增加输入长度和生成耗时。
- 因此全量主结果先用稳定配置，后续再单独 ablation。

使用 `ragas-batch-size=5`：

- 降低单次 RAGAS 调用压力。
- 每批写 checkpoint。
- 失败后可以 resume。

开启 context compression：

- 降低 token 压力。
- 提升全量运行稳定性。

### 全量结果

| Total | Scored | Faithfulness | Answer Relevancy | Answer Correctness |
|---:|---:|---:|---:|---:|
| 46 | 46 | 0.737 | 0.456 | 0.424 |

报告文件：

- `reports/ragas_eval_full_stable.md`
- `reports/ragas_eval_full_stable.json`
- `reports/ragas_eval_full_stable_checkpoint.json`

### 高分样例

Correctness Top 5：

| Question | Correctness | Relevancy | Faithfulness |
|---|---:|---:|---:|
| Q5 debt securities under 3M | 0.982 | 0.986 | 1.000 |
| Q31 Boeing product/service concentration | 0.965 | 0.956 | 1.000 |
| Q6 3M dividend trend | 0.958 | 0.994 | 0.818 |
| Q12 AMCOR industry | 0.949 | 1.000 | 1.000 |
| Q40 PepsiCo restructuring costs | 0.945 | 0.885 | 0.429 |

低分样例：

| Question | Correctness | Main Issue |
|---|---:|---|
| Q26 American Express largest liability | 0.144 | 需要更准确定位 balance sheet line item |
| Q3 3M organic segment drag | 0.148 | 需要表格/分部页精确召回 |
| Q8 AES inventory turnover | 0.150 | 需要 cost of sales 和 inventory 两个 line item |
| Q20 AMD customer concentration | 0.153 | 需要精确召回 risk/customer concentration 段落 |
| Q45 Ulta repurchase percentage | 0.157 | 需要 earnings release 表格计算 |

## 10. 阶段性结论

从 baseline 到最终全量测试，主要收益来自三类改进：

### 1. Prompt 从拒答型 QA 转为财务分析型 QA

改进点：

- 鼓励模型在证据支持下做简单计算。
- 要求输出 evidence、calculation、final answer。
- 避免因为最终指标没有直接出现而过度拒答。

收益：

- `answer_correctness` 在 5 题测试中从 0.359 提升到 0.413。

### 2. Finance Query Expansion 改善证据召回

改进点：

- 把自然语言问题扩展为财务 line item 查询。
- 对多路查询做 RRF 融合和 rerank。

收益：

- 5 题测试 `answer_correctness` 从 0.359 提升到 0.494。
- 5 题测试 `answer_relevancy` 从 0.199 提升到 0.358。

### 3. 工程化全量评测能力

改进点：

- RAGAS batch scoring。
- generation checkpoint。
- scoring checkpoint。
- resume。
- context compression。

收益：

- 46/46 全量评测成功完成。
- 中途失败后可以从 checkpoint 继续。
- 评测链路从一次性脚本变成可复现实验流程。

## 11. 当前不足

当前 `answer_correctness=0.424`，说明生成阶段仍有明显提升空间。

主要瓶颈不是单纯 prompt，而是 **表格和页面级证据召回**：

1. PDF 表格被文本抽取后结构丢失。
2. 一个财务指标经常需要多个 line items。
3. 多个 line items 可能分散在相邻 chunk 或不同页面。
4. 当前 chunk-level retrieval 对精确表格计算题仍不够稳定。

## 12. 下一步计划

### 1. Page-level Retrieval

为 FinanceBench 增加 page-level index：

- 按页存储 PDF text。
- metadata 中保留 `page_label` / `page_number`。
- 检索时先定位文档和页，再在页内抽 evidence。

目标：

- 改善 expected_pages 类型问题的召回。
- 特别是 balance sheet、income statement、cash flow statement。

### 2. Table-aware Extraction

针对财报表格做结构化抽取：

- 使用 pdfplumber / pymupdf 提取表格。
- 将表格转成 Markdown 或 JSON。
- 单独建立 table index。

目标：

- 提升 inventory turnover、quick ratio、gross margin、EBITDA 等计算题正确率。

### 3. Formula-aware Answering

对常见财务指标增加公式模板：

- quick ratio
- gross margin
- operating margin
- ROA
- inventory turnover
- EBITDA less capex

目标：

- 先抽取 line items。
- 再用 deterministic calculator 计算。
- 最后让 LLM 组织自然语言答案。

### 4. Ablation Study

后续需要系统比较：

- query expansion on/off
- context compression on/off
- neighbor-window 0/1/2
- generation-top-k 5/6/8
- page-level retrieval on/off
- table index on/off

这样项目可以形成更完整的实验闭环。

## 13. 可以写入简历的项目表述

可以把这一阶段总结成：

> 构建企业财报 RAG 生成评测链路，基于 FinanceBench 子集接入 RAGAS，对 faithfulness、answer relevancy、answer correctness 进行全量评测；针对财务问答中表格字段召回不足和模型过度拒答问题，设计 finance query expansion、evidence compression、generation top-k 调参与可恢复 batch evaluation 机制，将 5 题样本 answer correctness 从 0.359 提升至 0.494，并完成 46 题全量 RAGAS 评测。

如果想更工程化一点：

> 实现可恢复的 RAGAS 评测流水线，支持生成阶段 checkpoint、RAGAS batch scoring、resume、逐题 citation 追踪与失败样例分析，沉淀从检索命中率到生成质量的端到端评测闭环。

