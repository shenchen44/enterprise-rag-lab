import { useState } from "react";
import {
  Library,
  MessageSquare,
  FlaskConical,
  Activity,
  ArrowUpRight,
  ArrowRight,
  FileText,
  ChevronRight,
  Upload,
  ShieldCheck,
  Database,
} from "lucide-react";
import type { User, Overview, Document, Page } from "../types";
import { percent, bytes, date } from "../lib/format";
import { Badge, Empty, Metric } from "../components/ui";
import { DocumentModal } from "../components/documents";

export function Dashboard({
  data,
  user,
  onNavigate,
  onNewChat,
  onUpload,
  onError,
}: {
  data: Overview;
  user: User;
  onNavigate: (p: Page) => void;
  onNewChat: () => void;
  onUpload: () => void;
  onError: (s: string) => void;
}) {
  const optimized = data.evaluations.find((x) => x.id === "optimized"),
    latest = data.recentRuns.slice(0, 4),
    [preview, setPreview] = useState<Document | null>(null);
  return (
    <div className="dashboard page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">RESEARCH OVERVIEW</span>
          <h1>
            你好，{user.name}
            <span className="greeting-dot">.</span>
          </h1>
          <p>把散落的企业知识，变成有依据的洞察。</p>
        </div>
        <button className="button secondary" onClick={onUpload}>
          <Upload size={16} />
          上传文档
        </button>
      </div>
      <section className="welcome-banner">
        <div>
          <span className="banner-label">
            <span /> EVIDENCE-DRIVEN RESEARCH
          </span>
          <h2>好问题，值得一个可信的答案。</h2>
          <p>从财报到结论，在同一个工作台完成检索、问答与验证。</p>
          <button className="button banner-button" onClick={onNewChat}>
            开始研究 <ArrowRight size={16} />
          </button>
        </div>
        <div className="banner-art" aria-hidden="true">
          <div className="art-grid" />
          <div className="paper paper-back" />
          <div className="paper paper-front">
            <span className="paper-kicker">ANNUAL REPORT</span>
            <div className="paper-title">
              Knowledge,
              <br />
              connected.
            </div>
            <div className="paper-lines" />
            <div className="paper-chart">
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>
          <span className="art-badge">
            <ShieldCheck size={17} /> 可追溯的证据
          </span>
          <span className="art-spark">✳</span>
        </div>
      </section>
      <div className="metric-grid">
        <Metric
          icon={Library}
          label="知识库文档"
          value={String(data.documents.length)}
          detail={`${data.documents.filter((x) => x.kind === "benchmark").length} 份基准财报 · ${data.documents.filter((x) => x.kind === "upload").length} 份个人文档`}
          sub="DOCUMENTS"
        />
        <Metric
          icon={FlaskConical}
          label="评测问题"
          value={String(optimized?.questions || 0)}
          detail="FinanceBench · 真实财报问答"
          sub="BENCHMARK QUESTIONS"
        />
        <Metric
          icon={ShieldCheck}
          label="答案正确性"
          value={percent(optimized?.answerCorrectness)}
          detail="RAGAS · 证据槽位优化方案"
          sub="ANSWER CORRECTNESS"
        />
        <Metric
          icon={Activity}
          label="研究任务"
          value={String(data.runCount)}
          detail="当前账号的全部问答任务"
          sub="RESEARCH RUNS"
        />
      </div>
      <div className="dashboard-columns">
        <section className="panel knowledge-panel">
          <div className="panel-heading">
            <div>
              <h2>你的知识库</h2>
              <p>让下一次研究，从已有知识开始</p>
            </div>
            <button
              className="text-button"
              onClick={() => onNavigate("documents")}
            >
              查看全部 <ArrowUpRight size={15} />
            </button>
          </div>
          <div className="document-cards">
            {data.documents.slice(0, 4).map((d) => (
              <button
                className="document-card"
                key={d.id}
                onClick={() => setPreview(d)}
              >
                <div className="doc-card-top">
                  <span className="file-icon">
                    <FileText size={23} />
                  </span>
                  <span className="file-format">PDF</span>
                </div>
                <h3>{d.title}</h3>
                <span className="doc-sub">
                  {d.pages} 页 <i /> {bytes(d.bytes)}
                </span>
                <div className="doc-card-bottom">
                  <Badge status={d.status} />
                  <ArrowUpRight size={15} />
                </div>
              </button>
            ))}
          </div>
          {!data.documents.length && (
            <Empty
              title="开始建立你的知识库"
              description="上传文档，或同步项目中的基准财报。"
              action={
                <button className="button secondary" onClick={onUpload}>
                  上传第一份文档
                </button>
              }
            />
          )}
        </section>
        <section className="panel experiment-panel">
          <div className="panel-heading">
            <div>
              <h2>实验快照</h2>
              <p>从真实评测报告观察迭代效果</p>
            </div>
            <span className="tiny-pill">RAGAS</span>
          </div>
          <div className="experiment-main">
            <span>Answer correctness</span>
            <strong>{percent(optimized?.answerCorrectness)}</strong>
            <small>证据槽位优化 · {optimized?.questions || 0} 道问题</small>
          </div>
          <div className="comparison-bars">
            {data.evaluations.map((e, i) => (
              <div key={e.id}>
                <span>{e.name}</span>
                <div className="bar-track">
                  <i
                    style={{ width: percent(e.answerCorrectness) }}
                    className={"bar-" + i}
                  />
                </div>
                <strong>{percent(e.answerCorrectness)}</strong>
              </div>
            ))}
          </div>
          <p className="source-caption">
            <Database size={12} />
            读取项目已有报告，非实时评测
          </p>
          <button
            className="text-button"
            onClick={() => onNavigate("evaluations")}
          >
            查看完整评测 <ArrowRight size={15} />
          </button>
        </section>
      </div>
      <section className="panel recent-panel">
        <div className="panel-heading">
          <div>
            <h2>最近研究</h2>
            <p>每次提问，都有完整的执行记录</p>
          </div>
          <button className="text-button" onClick={() => onNavigate("runs")}>
            全部任务 <ArrowUpRight size={15} />
          </button>
        </div>
        {latest.length ? (
          <div className="recent-list">
            {latest.map((r) => (
              <button key={r.id} onClick={() => onNavigate("runs")}>
                <span className="recent-icon">
                  <MessageSquare size={17} />
                </span>
                <div>
                  <strong>{r.question}</strong>
                  <small>
                    {r.mode === "live" ? "模型问答" : "证据预览"} ·{" "}
                    {date(r.createdAt)}
                  </small>
                </div>
                <Badge status={r.status} />
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        ) : (
          <div className="recent-empty">
            <MessageSquare size={22} />
            <div>
              <strong>你的第一段研究，即将开始</strong>
              <p>选择一份财报，问一个你关心的问题。</p>
            </div>
            <button className="button secondary small" onClick={onNewChat}>
              开始提问 <ArrowRight size={14} />
            </button>
          </div>
        )}
      </section>
      {preview && (
        <DocumentModal
          document={preview}
          onClose={() => setPreview(null)}
          onError={onError}
        />
      )}
    </div>
  );
}
