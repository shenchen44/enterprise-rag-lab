import { useState, useEffect } from "react";
import {
  Search,
  FileText,
  ChevronRight,
  CheckCircle2,
  ShieldCheck,
  LoaderCircle,
  BookOpen,
  Database,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import type { Evaluation, EvalDetail, EvalRow } from "../types";
import { percent } from "../lib/format";
import { Empty, Modal, Metric } from "../components/ui";

export function Evaluations({
  evaluations,
  onError,
}: {
  evaluations: Evaluation[];
  onError: (s: string) => void;
}) {
  const [selected, setSelected] = useState("optimized"),
    [detail, setDetail] = useState<EvalDetail | null>(null),
    [search, setSearch] = useState(""),
    [row, setRow] = useState<EvalRow | null>(null),
    [loading, setLoading] = useState(false),
    [evalPage, setEvalPage] = useState(1);
  useEffect(() => setEvalPage(1), [selected, search]);
  useEffect(() => {
    let stop = false;
    setLoading(true);
    api<EvalDetail>("/evaluations/" + selected)
      .then((d) => {
        if (!stop) setDetail(d);
      })
      .catch((e) => onError(e.message))
      .finally(() => {
        if (!stop) setLoading(false);
      });
    return () => {
      stop = true;
    };
  }, [selected, onError]);
  const current = evaluations.find((e) => e.id === selected);
  const rows =
    detail?.rows.filter((r) =>
      r.question.toLowerCase().includes(search.toLowerCase()),
    ) || [];
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">EVALUATION STUDIO</span>
          <h1>衡量每一次进步。</h1>
          <p>对比真实实验，理解答案质量与证据检索的变化。</p>
        </div>
        <span className="report-source">
          <Database size={15} />
          已有报告 · 只读分析
        </span>
      </div>
      <div className="evaluation-compare">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>方案对比</h2>
              <p>FinanceBench · 同一批 {current?.questions || 46} 道问题</p>
            </div>
            <span className="tiny-pill">3 个实验方案</span>
          </div>
          <div className="evaluation-table">
            <table>
              <thead>
                <tr>
                  <th>实验方案</th>
                  <th>证据页命中率</th>
                  <th>答案正确性</th>
                  <th>上下文召回</th>
                  <th>忠实度</th>
                </tr>
              </thead>
              <tbody>
                {evaluations.map((e) => (
                  <tr
                    key={e.id}
                    className={selected === e.id ? "selected-row" : ""}
                    onClick={() => setSelected(e.id)}
                  >
                    <td>
                      <button
                        className="experiment-select"
                        onClick={() => setSelected(e.id)}
                      >
                        <span
                          className={
                            "radio " + (selected === e.id ? "checked" : "")
                          }
                        />
                        <strong>{e.name}</strong>
                        {e.id === "optimized" && (
                          <span className="best-label">当前方案</span>
                        )}
                      </button>
                    </td>
                    <td>{percent(e.pageHitRate)}</td>
                    <td className="numeric-emphasis">
                      {percent(e.answerCorrectness)}
                    </td>
                    <td>{percent(e.contextRecall)}</td>
                    <td>{percent(e.faithfulness)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="report-note">
            <ShieldCheck size={15} />
            <span>
              指标直接读取项目已有 JSON
              报告。检索与生成来自各自报告，数值仅代表该固定评测集。
            </span>
          </div>
        </section>
      </div>
      <div className="eval-stats">
        <Metric
          icon={Search}
          label="证据页命中率"
          value={percent(current?.pageHitRate)}
          detail="检索证据是否落在参考页"
          sub="EVIDENCE PAGE HIT"
        />
        <Metric
          icon={CheckCircle2}
          label="答案正确性"
          value={percent(current?.answerCorrectness)}
          detail="RAGAS Answer Correctness"
          sub="GENERATION QUALITY"
        />
        <Metric
          icon={BookOpen}
          label="上下文召回"
          value={percent(current?.contextRecall)}
          detail="RAGAS Context Recall"
          sub="CONTEXT RECALL"
        />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>
              逐题检查{" "}
              <span className="heading-count">{detail?.rows.length || 0}</span>
            </h2>
            <p>{current?.name} · 查看回答、参考答案与证据页</p>
          </div>
          <div className="inline-search">
            <Search size={15} />
            <input
              aria-label="搜索评测问题"
              placeholder="搜索问题…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        {loading ? (
          <div className="page-loading">
            <LoaderCircle className="spin" />
            正在读取报告
          </div>
        ) : (
          <div className="eval-rows">
            {rows.slice((evalPage - 1) * 10, evalPage * 10).map((r) => (
              <button key={r.id} onClick={() => setRow(r)}>
                <span className="question-number">
                  {String(r.id + 1).padStart(2, "0")}
                </span>
                <div>
                  <strong>{r.question}</strong>
                  <small>
                    {r.sources.join(" · ")}{" "}
                    {r.pages.length ? "· 参考页 " + r.pages.join(", ") : ""}
                  </small>
                </div>
                <span
                  className={
                    "evaluation-hit " + (r.retrieval.page_hit ? "hit" : "miss")
                  }
                >
                  {r.retrieval.page_hit ? "证据页命中" : "未命中参考页"}
                </span>
                <ChevronRight size={16} />
              </button>
            ))}
            {!rows.length && (
              <Empty
                icon={Search}
                title="没有匹配问题"
                description="请调整搜索词或切换实验方案。"
              />
            )}
          </div>
        )}
        <div className="table-footer evaluation-footer">
          <span>
            共 {rows.length} 道问题 · 第 {evalPage} /{" "}
            {Math.max(1, Math.ceil(rows.length / 10))} 页
          </span>
          <div className="pagination">
            <button
              className="button secondary small"
              disabled={evalPage === 1}
              onClick={() => setEvalPage((p) => p - 1)}
            >
              上一页
            </button>
            <button
              className="button secondary small"
              disabled={evalPage * 10 >= rows.length}
              onClick={() => setEvalPage((p) => p + 1)}
            >
              下一页
            </button>
          </div>
        </div>
        <div className="source-files">
          来源：{detail?.sourceFiles.join(" / ") || "—"}
        </div>
      </section>
      {row && (
        <Modal
          title={"评测问题 " + (row.id + 1)}
          onClose={() => setRow(null)}
          wide
        >
          <div className="eval-detail">
            <span className="eyebrow">QUESTION</span>
            <h3>{row.question}</h3>
            <div className="eval-detail-columns">
              <section>
                <span className="section-tag">模型回答</span>
                <div className="markdown">
                  <ReactMarkdown disallowedElements={["img"]}>
                    {row.answer || "该报告未保存生成回答。"}
                  </ReactMarkdown>
                </div>
              </section>
              <section>
                <span className="section-tag green">参考答案</span>
                <div className="markdown">
                  <ReactMarkdown disallowedElements={["img"]}>
                    {row.reference || "该报告未保存参考答案。"}
                  </ReactMarkdown>
                </div>
              </section>
            </div>
            <div className="report-note">
              <FileText size={16} />
              {row.sources.join(", ")} · 参考页 {row.pages.join(", ")}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
