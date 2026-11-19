import { useState, useEffect, useRef } from "react";
import type { FormEvent } from "react";
import {
  Library,
  MessageSquare,
  Plus,
  ArrowUpRight,
  ArrowUp,
  Search,
  FileText,
  ChevronDown,
  Check,
  MoreHorizontal,
  Trash2,
  ShieldCheck,
  LoaderCircle,
  Square,
  PanelLeftClose,
  Layers,
  BookOpen,
  Link2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, streamRun } from "../api";
import type { Document, Conversation, Message, Run, Citation } from "../types";
import { active } from "../lib/format";
import { Badge, Modal } from "../components/ui";

const prompts = [
  {
    label: "理解企业经营",
    question: "What were 3M’s net sales in fiscal year 2022?",
    icon: BookOpen,
  },
  {
    label: "查找财务指标",
    question: "What was AMD’s revenue in 2022?",
    icon: Search,
  },
  {
    label: "分析财报证据",
    question: "Is 3M a capital-intensive business based on FY2022 data?",
    icon: Layers,
  },
  {
    label: "检查来源与引用",
    question: "What drove operating margin change as of FY2022 for 3M?",
    icon: ShieldCheck,
  },
];

export function Chat({
  docs,
  conversations,
  conversationId,
  onSelect,
  onRefresh,
  onError,
  onCitation,
  modelConfigured,
}: {
  docs: Document[];
  conversations: Conversation[];
  conversationId: string | null;
  onSelect: (id: string | null) => void;
  onRefresh: () => Promise<void>;
  onError: (s: string) => void;
  onCitation: (c: Citation) => void;
  modelConfigured: boolean;
}) {
  const [messages, setMessages] = useState<Message[]>([]),
    [question, setQuestion] = useState(""),
    [mode, setMode] = useState("evidence"),
    [scope, setScope] = useState<string[]>([]),
    [run, setRun] = useState<Run | null>(null),
    [sending, setSending] = useState(false),
    [scopeOpen, setScopeOpen] = useState(false),
    [historyOpen, setHistoryOpen] = useState(true),
    [rename, setRename] = useState<Conversation | null>(null),
    [renameValue, setRenameValue] = useState("");
  const end = useRef<HTMLDivElement>(null),
    text = useRef<HTMLTextAreaElement>(null),
    currentId = useRef(conversationId);
  currentId.current = conversationId;
  useEffect(() => {
    let cancelled = false;
    setRun(null);
    setMessages([]);
    if (conversationId) {
      Promise.all([
        api<Message[]>("/conversations/" + conversationId + "/messages"),
        api<Run[]>("/runs"),
      ])
        .then(([m, r]) => {
          if (!cancelled) {
            setMessages(m);
            setRun(
              r.find(
                (x) => x.conversationId === conversationId && active(x.status),
              ) || null,
            );
          }
        })
        .catch((e) => onError(e.message));
    }
    return () => {
      cancelled = true;
    };
  }, [conversationId, onError]);
  const runId = run?.id;
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setInterval> | undefined;
    const id = run?.conversationId;
    const update = (r: Run) => {
      if (currentId.current !== id) return;
      setRun(r);
      if (!active(r.status)) {
        void api<Message[]>("/conversations/" + id + "/messages")
          .then(setMessages)
          .catch(() => {});
        void onRefresh();
        if (timer) clearInterval(timer);
      }
    };
    void streamRun(runId, update, controller.signal).catch((e) => {
      if (e.name === "AbortError") return;
      timer = setInterval(() => {
        void api<Run>("/runs/" + runId)
          .then(update)
          .catch(() => {
            if (timer) clearInterval(timer);
          });
      }, 1200);
    });
    return () => {
      controller.abort();
      if (timer) clearInterval(timer);
    };
    // A run keeps its own stream until completion; snapshots must not reconnect it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, run?.answer, run?.status]);
  async function send(e?: FormEvent) {
    e?.preventDefault();
    const q = question.trim();
    if (!q || sending || (run && active(run.status))) return;
    setSending(true);
    try {
      let id = conversationId;
      if (!id) {
        const c = await api<Conversation>("/conversations", { method: "POST" });
        id = c.id;
        onSelect(id);
      }
      const r = await api<Run>("/conversations/" + id + "/messages", {
        method: "POST",
        body: JSON.stringify({
          question: q,
          mode,
          documentIds: scope,
          idempotencyKey: crypto.randomUUID(),
        }),
      });
      setQuestion("");
      setRun(r);
      setMessages(await api<Message[]>("/conversations/" + id + "/messages"));
      void onRefresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSending(false);
    }
  }
  async function remove(c: Conversation) {
    if (!confirm("删除该会话及其消息和任务记录？")) return;
    try {
      await api("/conversations/" + c.id, { method: "DELETE" });
      if (c.id === conversationId) onSelect(null);
      await onRefresh();
    } catch (e) {
      onError((e as Error).message);
    }
  }
  const busy = !!run && active(run.status),
    visible = messages.filter((m) => !(run && m.id === run.messageId));
  return (
    <div className={"chat-layout " + (!historyOpen ? "history-hidden" : "")}>
      <aside className="chat-history">
        <div className="chat-history-head">
          <span>研究会话</span>
          <button
            className="icon-button"
            title="新建会话"
            aria-label="新建会话"
            onClick={() => onSelect(null)}
          >
            <Plus size={17} />
          </button>
        </div>
        <button
          className="new-thread"
          onClick={() => {
            onSelect(null);
            setQuestion("");
            text.current?.focus();
          }}
        >
          <Plus size={16} />
          开始新的研究
        </button>
        <span className="history-label">全部会话 · {conversations.length}</span>
        <div className="history-items">
          {conversations.map((c) => (
            <div
              className={
                "history-item " + (c.id === conversationId ? "active" : "")
              }
              key={c.id}
            >
              <button className="history-select" onClick={() => onSelect(c.id)}>
                <MessageSquare size={15} />
                <span>{c.title}</span>
              </button>
              <div className="history-actions">
                <button
                  title="重命名"
                  aria-label={"重命名 " + c.title}
                  onClick={() => {
                    setRename(c);
                    setRenameValue(c.title);
                  }}
                >
                  <MoreHorizontal size={14} />
                </button>
                <button
                  title="删除"
                  aria-label={"删除会话 " + c.title}
                  onClick={() => void remove(c)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
          {!conversations.length && (
            <p className="history-no-items">你的研究会话会保存在这里。</p>
          )}
        </div>
        <div className="history-foot">
          <ShieldCheck size={15} />
          <span>会话仅对当前账号可见</span>
        </div>
      </aside>
      <section className="chat-main">
        <div className="chat-top">
          <button
            className="icon-button"
            title="切换会话侧栏"
            aria-label="切换会话侧栏"
            onClick={() => setHistoryOpen(!historyOpen)}
          >
            <PanelLeftClose size={18} />
          </button>
          <strong>
            {conversations.find((c) => c.id === conversationId)?.title ||
              "新的研究"}
          </strong>
          <span className="chat-top-label">
            <span /> GROUNDED IN YOUR DOCUMENTS
          </span>
        </div>
        <div className="chat-scroll">
          {!messages.length && !run ? (
            <div className="chat-welcome">
              <span className="assistant-emblem">
                <Layers size={29} />
              </span>
              <span className="eyebrow">RESEARCH ASSISTANT</span>
              <h1>从一个好问题开始。</h1>
              <p>查找财报里的答案，让每个结论连接原文。</p>
              <div className="prompt-grid">
                {prompts.map(({ label, question, icon: Icon }) => (
                  <button
                    key={label}
                    onClick={() => {
                      setQuestion(question);
                      text.current?.focus();
                    }}
                  >
                    <Icon size={18} />
                    <strong>{label}</strong>
                    <span>{question}</span>
                    <ArrowUpRight size={15} />
                  </button>
                ))}
              </div>
              <span className="chat-welcome-note">
                <Link2 size={13} /> 支持来源引用 · 文档范围选择 · 执行过程查看
              </span>
            </div>
          ) : (
            <div className="message-list">
              {visible.map((m) => (
                <MessageBubble key={m.id} message={m} onCitation={onCitation} />
              ))}
              {run && (
                <MessageBubble
                  message={{
                    id: run.messageId,
                    role: "assistant",
                    content: run.answer || "",
                    status: run.status,
                    citations: run.citations || [],
                    trace: run.trace || [],
                    createdAt: run.createdAt,
                  }}
                  onCitation={onCitation}
                  error={run.error}
                  mode={run.mode}
                />
              )}
              <div ref={end} />
            </div>
          )}
        </div>
        <div className="composer-area">
          <form className="composer" onSubmit={(e) => void send(e)}>
            <textarea
              ref={text}
              aria-label="输入研究问题"
              placeholder="询问文档中的信息，例如：3M 在 2022 年的净销售额是多少？"
              value={question}
              maxLength={4000}
              rows={2}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <div className="composer-bottom">
              <div className="composer-tools">
                <div className="scope-control">
                  <button
                    type="button"
                    className={"scope-button " + (scope.length ? "scoped" : "")}
                    onClick={() => setScopeOpen(!scopeOpen)}
                  >
                    <Library size={14} />
                    {scope.length
                      ? `已选择 ${scope.length} 份文档`
                      : "全部可访问文档"}
                    <ChevronDown size={13} />
                  </button>
                  {scopeOpen && (
                    <div className="scope-menu">
                      <div>
                        <strong>选择检索范围</strong>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => setScope([])}
                        >
                          全部
                        </button>
                      </div>
                      {docs
                        .filter((d) => d.status === "READY")
                        .map((d) => (
                          <label key={d.id}>
                            <input
                              type="checkbox"
                              checked={scope.includes(d.id)}
                              onChange={(e) =>
                                setScope((v) =>
                                  e.target.checked
                                    ? [...v, d.id]
                                    : v.filter((x) => x !== d.id),
                                )
                              }
                            />
                            <span>{d.title}</span>
                          </label>
                        ))}
                      <button
                        type="button"
                        className="button primary small full"
                        onClick={() => setScopeOpen(false)}
                      >
                        完成选择
                      </button>
                    </div>
                  )}
                </div>
                <select
                  aria-label="问答模式"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={busy}
                >
                  <option value="evidence">证据预览 · 不调用模型</option>
                  <option value="live" disabled={!modelConfigured}>
                    模型问答{!modelConfigured ? " · 暂不可用" : ""}
                  </option>
                </select>
              </div>
              {busy ? (
                <button
                  type="button"
                  className="send-button stop"
                  aria-label="停止生成"
                  title="停止生成"
                  onClick={async () => {
                    try {
                      setRun(
                        await api<Run>("/runs/" + run.id + "/cancel", {
                          method: "POST",
                        }),
                      );
                    } catch (e) {
                      onError((e as Error).message);
                    }
                  }}
                >
                  <Square size={16} />
                </button>
              ) : (
                <button
                  className="send-button"
                  aria-label="发送问题"
                  disabled={!question.trim() || sending}
                >
                  {sending ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <ArrowUp size={20} />
                  )}
                </button>
              )}
            </div>
          </form>
          <div className="composer-note">
            <span>
              {mode === "evidence"
                ? "证据模式直接摘录原文，不生成模型结论。"
                : "模型可能出错，请结合引用核对关键事实。"}
            </span>
            <span>Enter 发送 · Shift + Enter 换行</span>
          </div>
        </div>
      </section>
      {rename && (
        <Modal title="重命名会话" onClose={() => setRename(null)}>
          <form
            className="rename-form"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api("/conversations/" + rename.id, {
                  method: "PATCH",
                  body: JSON.stringify({ title: renameValue }),
                });
                setRename(null);
                await onRefresh();
              } catch (e) {
                onError((e as Error).message);
              }
            }}
          >
            <input
              aria-label="会话名称"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              maxLength={120}
              required
            />
            <button className="button primary">保存名称</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

export function MessageBubble({
  message: m,
  onCitation,
  error,
  mode,
}: {
  message: Message;
  onCitation: (c: Citation) => void;
  error?: string;
  mode?: string;
}) {
  const [traceOpen, setTraceOpen] = useState(false);
  if (m.role === "user")
    return (
      <article className="message user-message">
        <span className="message-avatar human">你</span>
        <div>
          <span className="message-author">你</span>
          <p>{m.content}</p>
        </div>
      </article>
    );
  return (
    <article className="message assistant-message">
      <span className="message-avatar assistant">
        <Layers size={17} />
      </span>
      <div className="message-body">
        <div className="message-author">
          研究助手{" "}
          <span>
            {mode === "live"
              ? "模型问答"
              : mode === "evidence"
                ? "证据预览"
                : ""}
          </span>
          {active(m.status) && <LoaderCircle size={13} className="spin" />}
        </div>
        {m.trace.length > 0 && (
          <div className="trace-block">
            <button onClick={() => setTraceOpen(!traceOpen)}>
              <span
                className={"trace-dot " + (active(m.status) ? "pulsing" : "")}
              />
              {active(m.status)
                ? m.trace[m.trace.length - 1].stage
                : "查看执行过程"}
              <ChevronDown size={13} className={traceOpen ? "rotated" : ""} />
              <small>{m.trace.length} 个阶段</small>
            </button>
            {traceOpen && (
              <ol>
                {m.trace.map((t, i) => (
                  <li key={i}>
                    <Check size={12} />
                    <div>
                      <strong>{t.stage}</strong>
                      <p>{t.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
        {m.content ? (
          <div className="markdown">
            <ReactMarkdown disallowedElements={["img"]}>
              {m.content}
            </ReactMarkdown>
          </div>
        ) : active(m.status) ? (
          <div className="thinking">
            <i />
            <i />
            <i />
            <span>正在检索你的文档</span>
          </div>
        ) : (
          <p className="muted">{error || "该任务没有生成完整回答。"}</p>
        )}
        {m.citations.length > 0 && (
          <div className="citations">
            <div>
              <Link2 size={13} />
              来源证据 <span>{m.citations.length}</span>
            </div>
            <div className="citation-chips">
              {m.citations.map((c, i) => (
                <button key={c.id} onClick={() => onCitation(c)}>
                  <b>{i + 1}</b>
                  <FileText size={13} />
                  <span>{c.fileName}</span>
                  <small>p.{c.page}</small>
                  <ArrowUpRight size={12} />
                </button>
              ))}
            </div>
          </div>
        )}
        {!active(m.status) && (
          <div className="message-foot">
            <Badge status={m.status} />
            {error && <span className="message-error">{error}</span>}
          </div>
        )}
      </div>
    </article>
  );
}
