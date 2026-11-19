import { useState, useEffect, useCallback } from "react";
import {
  LayoutDashboard,
  Library,
  MessageSquare,
  FlaskConical,
  Activity,
  Plus,
  ArrowUpRight,
  Search,
  ChevronRight,
  ChevronDown,
  MoreHorizontal,
  X,
  LogOut,
  LoaderCircle,
  Layers,
  BookOpen,
  AlertCircle,
  Settings2,
  Menu,
} from "lucide-react";
import { api, setToken } from "./api";
import type { User, Overview, Conversation, Citation, Page } from "./types";
import { Brand, Modal } from "./components/ui";
import { UploadModal, CitationPanel } from "./components/documents";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Documents } from "./pages/Documents";
import { Chat } from "./pages/Chat";
import { Evaluations } from "./pages/Evaluations";
import { Runs } from "./pages/Runs";

const pages: { id: Page; label: string; icon: typeof Library }[] = [
  { id: "overview", label: "研究概览", icon: LayoutDashboard },
  { id: "documents", label: "知识库", icon: Library },
  { id: "chat", label: "智能问答", icon: MessageSquare },
  { id: "evaluations", label: "评测中心", icon: FlaskConical },
  { id: "runs", label: "任务记录", icon: Activity },
];

export default function App() {
  const [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(true),
    [page, setPage] = useState<Page>("overview"),
    [data, setData] = useState<Overview | null>(null),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<string | null>(null),
    [globalSearch, setGlobalSearch] = useState(""),
    [uploadOpen, setUploadOpen] = useState(false),
    [citation, setCitation] = useState<Citation | null>(null),
    [settings, setSettings] = useState(false),
    [mobile, setMobile] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setData(await api<Overview>("/overview"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setToken(""))
      .finally(() => setBoot(false));
    const fn = () => {
      setToken("");
      setUser(null);
      setData(null);
    };
    window.addEventListener("rag:unauthorized", fn);
    return () => window.removeEventListener("rag:unauthorized", fn);
  }, []);
  useEffect(() => {
    if (user) void refresh();
  }, [user, refresh]);
  useEffect(() => {
    if (error) {
      const t = setTimeout(() => setError(""), 9000);
      return () => clearTimeout(t);
    }
  }, [error]);
  function navigate(p: Page) {
    setPage(p);
    setMobile(false);
  }
  async function newChat() {
    try {
      const c = await api<Conversation>("/conversations", { method: "POST" });
      setSelected(c.id);
      navigate("chat");
      void refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (boot)
    return (
      <div className="boot">
        <Layers size={32} />
        <LoaderCircle size={20} className="spin" />
        <span>正在连接研究工作台</span>
      </div>
    );
  return (
    <>
      {error && (
        <div role="alert" className="toast">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button aria-label="关闭提示" onClick={() => setError("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {!user ? (
        <Login onLogin={setUser} onError={setError} />
      ) : (
        <div className="app-shell">
          <aside className={"sidebar " + (mobile ? "open" : "")}>
            <Brand />
            <button
              className="workspace-button"
              onClick={() => setSettings(true)}
            >
              <span className="workspace-avatar">R</span>
              <span>
                <strong>个人研究空间</strong>
                <small>Research workspace</small>
              </span>
              <ChevronDown size={15} />
            </button>
            <div className="nav-label">工作空间</div>
            <nav>
              {pages.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  className={"nav-item " + (page === id ? "selected" : "")}
                  onClick={() => navigate(id)}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                  {id === "documents" && <b>{data?.documents.length || 0}</b>}
                  {id === "chat" && <small className="nav-new">AI</small>}
                </button>
              ))}
            </nav>
            <div className="sidebar-note">
              <span className="mini-symbol">
                <BookOpen size={18} />
              </span>
              <strong>每个结论，都回到原文</strong>
              <p>在引用面板中核对文档来源、页码与证据内容。</p>
              <button onClick={() => navigate("chat")}>
                开始一次研究 <ArrowUpRight size={14} />
              </button>
            </div>
            <div className="sidebar-bottom">
              <span
                className={
                  "service-dot " +
                  (data?.agent.status === "ready" ? "" : "offline")
                }
              />
              <span>
                {data?.agent.status === "ready"
                  ? "研究服务已连接"
                  : "推理服务未连接"}
              </span>
              <button
                aria-label="查看服务信息"
                onClick={() => setSettings(true)}
              >
                <Settings2 size={15} />
              </button>
            </div>
            <button className="user-card" onClick={() => setSettings(true)}>
              <span className="avatar">{user.name.slice(0, 1)}</span>
              <span>
                <strong>{user.name}</strong>
                <small>个人账号</small>
              </span>
              <MoreHorizontal size={18} />
            </button>
          </aside>
          <div className="main-shell">
            <header className="topbar">
              <div className="breadcrumb">
                <button
                  className="mobile-menu icon-button"
                  onClick={() => setMobile(!mobile)}
                  aria-label="打开导航"
                >
                  <Menu size={20} />
                </button>
                <span>工作空间</span>
                <ChevronRight size={14} />
                <strong>{pages.find((p) => p.id === page)?.label}</strong>
              </div>
              <div className="top-actions">
                <form
                  className="global-search"
                  onSubmit={(e) => {
                    e.preventDefault();
                    navigate("documents");
                  }}
                >
                  <Search size={16} />
                  <input
                    aria-label="搜索文档"
                    placeholder="搜索你的文档…"
                    value={globalSearch}
                    onChange={(e) => setGlobalSearch(e.target.value)}
                  />
                  <kbd>↵</kbd>
                </form>
                <button className="button primary small" onClick={newChat}>
                  <Plus size={16} />
                  新建对话
                </button>
              </div>
            </header>
            <main
              className={"content " + (page === "chat" ? "chat-content" : "")}
            >
              {!data ? (
                <div className="page-loading">
                  <LoaderCircle className="spin" />
                  正在载入工作台…
                </div>
              ) : (
                <>
                  {page === "overview" && (
                    <Dashboard
                      data={data}
                      user={user}
                      onNavigate={navigate}
                      onNewChat={newChat}
                      onUpload={() => setUploadOpen(true)}
                      onError={setError}
                    />
                  )}
                  {page === "documents" && (
                    <Documents
                      docs={data.documents}
                      search={globalSearch}
                      onSearch={setGlobalSearch}
                      onUpload={() => setUploadOpen(true)}
                      onRefresh={refresh}
                      onError={setError}
                    />
                  )}
                  {page === "chat" && (
                    <Chat
                      docs={data.documents}
                      conversations={data.conversations}
                      conversationId={selected}
                      onSelect={setSelected}
                      onRefresh={refresh}
                      onError={setError}
                      onCitation={setCitation}
                      modelConfigured={
                        data.agent.modelConfigured &&
                        data.agent.modelStatus !== "auth_error"
                      }
                    />
                  )}
                  {page === "evaluations" && (
                    <Evaluations
                      evaluations={data.evaluations}
                      onError={setError}
                    />
                  )}
                  {page === "runs" && (
                    <Runs
                      onError={setError}
                      onOpen={(r) => {
                        setSelected(r.conversationId);
                        navigate("chat");
                      }}
                    />
                  )}
                </>
              )}
            </main>
            <footer className="app-footer">
              <span>
                Enterprise RAG Lab <i /> 让研究有据可循
              </span>
              <span>Java × Python · 本地工作空间</span>
            </footer>
          </div>
        </div>
      )}
      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onDone={() => {
            void refresh();
            navigate("documents");
          }}
          onError={setError}
        />
      )}{" "}
      {citation && (
        <CitationPanel
          citation={citation}
          onClose={() => setCitation(null)}
          onError={setError}
        />
      )}{" "}
      {settings && user && (
        <Modal title="工作空间设置" onClose={() => setSettings(false)}>
          <div className="settings-body">
            <div className="profile-big">
              <span className="avatar">{user.name.slice(0, 1)}</span>
              <div>
                <h3>{user.name}</h3>
                <p>{user.email}</p>
              </div>
            </div>
            <div className="settings-row">
              <span>业务后端</span>
              <strong>Spring Boot · 已连接</strong>
            </div>
            <div className="settings-row">
              <span>RAG 推理服务</span>
              <strong>
                {data?.agent.status === "ready" ? "Python · 已连接" : "未连接"}
              </strong>
            </div>
            <div className="settings-row">
              <span>模型配置</span>
              <strong>
                {data?.agent.modelStatus === "auth_error"
                  ? "模型认证失败，证据预览可用"
                  : data?.agent.modelConfigured
                    ? "已配置模型凭证，调用时验证"
                    : "未配置，可使用证据预览"}
              </strong>
            </div>
            <p className="muted">
              模型密钥只在服务器端读取，不会发送至浏览器。公共财报可共享阅读，上传文档与会话按账号隔离。
            </p>
            <button
              className="button danger"
              onClick={async () => {
                try {
                  await api("/auth/logout", { method: "POST" });
                } finally {
                  setToken("");
                  setUser(null);
                  setData(null);
                  setSettings(false);
                }
              }}
            >
              <LogOut size={16} />
              退出登录
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
