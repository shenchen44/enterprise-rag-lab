import { useState, useEffect } from "react";
import {
  Library,
  Plus,
  Search,
  FileText,
  Trash2,
  ShieldCheck,
  ExternalLink,
  RefreshCw,
} from "lucide-react";
import { api } from "../api";
import type { Document } from "../types";
import { bytes } from "../lib/format";
import { Badge, Empty } from "../components/ui";
import { DocumentModal } from "../components/documents";

export function Documents({
  docs,
  search,
  onSearch,
  onUpload,
  onRefresh,
  onError,
}: {
  docs: Document[];
  search: string;
  onSearch: (s: string) => void;
  onUpload: () => void;
  onRefresh: () => Promise<void>;
  onError: (s: string) => void;
}) {
  const [tab, setTab] = useState("all"),
    [preview, setPreview] = useState<Document | null>(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (docs.some((x) => x.status === "PROCESSING")) {
      const t = setInterval(() => void onRefresh(), 2000);
      return () => clearInterval(t);
    }
  }, [docs, onRefresh]);
  const filtered = docs.filter(
    (d) =>
      (tab === "all" || d.kind === tab) &&
      (d.title + " " + d.fileName).toLowerCase().includes(search.toLowerCase()),
  );
  async function sync() {
    setBusy(true);
    try {
      await api("/documents/sync", { method: "POST" });
      await onRefresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">KNOWLEDGE LIBRARY</span>
          <h1>你的知识，井然有序。</h1>
          <p>管理研究资料，查看解析状态，随时回到原文。</p>
        </div>
        <button className="button primary" onClick={onUpload}>
          <Plus size={17} />
          上传文档
        </button>
      </div>
      <div className="library-summary">
        <Library size={21} />
        <strong>{docs.length} 份文档</strong>
        <span>
          {docs.reduce((a, d) => a + d.pages, 0).toLocaleString()} 页可查阅资料
        </span>
        <span className="summary-divider" />
        <ShieldCheck size={15} />
        <span>个人上传仅对当前账号可见</span>
      </div>
      <section className="panel">
        <div className="table-toolbar">
          <div className="tabs">
            {[
              ["all", "全部文档"],
              ["benchmark", "基准财报"],
              ["upload", "个人上传"],
            ].map(([id, label]) => (
              <button
                className={tab === id ? "active" : ""}
                key={id}
                onClick={() => setTab(id)}
              >
                {label}
                <small>
                  {docs.filter((d) => id === "all" || d.kind === id).length}
                </small>
              </button>
            ))}
          </div>
          <div className="toolbar-right">
            <div className="inline-search">
              <Search size={15} />
              <input
                aria-label="筛选文档"
                placeholder="按名称筛选"
                value={search}
                onChange={(e) => onSearch(e.target.value)}
              />
            </div>
            <button
              className="icon-button"
              title="同步基准财报"
              aria-label="同步基准财报"
              disabled={busy}
              onClick={sync}
            >
              <RefreshCw size={16} className={busy ? "spin" : ""} />
            </button>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>文档名称</th>
                <th>来源</th>
                <th>页数</th>
                <th>大小</th>
                <th>状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id}>
                  <td>
                    <button className="file-name" onClick={() => setPreview(d)}>
                      <span className="file-icon small">
                        <FileText size={18} />
                      </span>
                      <span>
                        <strong>{d.title}</strong>
                        <small>{d.fileName}</small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <span className="source-tag">
                      {d.kind === "benchmark" ? "FinanceBench" : "个人上传"}
                    </span>
                  </td>
                  <td>{d.pages || "—"}</td>
                  <td>{bytes(d.bytes)}</td>
                  <td>
                    <Badge status={d.status} />
                    {d.error && (
                      <small className="error-caption">{d.error}</small>
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      {d.kind === "upload" && d.status === "FAILED" && (
                        <button
                          className="icon-button"
                          title="重试解析"
                          aria-label={"重试解析 " + d.title}
                          onClick={async () => {
                            try {
                              await api("/documents/" + d.id + "/retry", {
                                method: "POST",
                              });
                              await onRefresh();
                            } catch (e) {
                              onError((e as Error).message);
                            }
                          }}
                        >
                          <RefreshCw size={15} />
                        </button>
                      )}
                      <button
                        className="icon-button"
                        title="查看文档"
                        aria-label={"查看 " + d.title}
                        onClick={() => setPreview(d)}
                      >
                        <ExternalLink size={16} />
                      </button>
                      {d.kind === "upload" && (
                        <button
                          className="icon-button danger-icon"
                          title="删除文档"
                          aria-label={"删除 " + d.title}
                          onClick={async () => {
                            if (
                              !confirm("删除文档及其检索内容？历史消息会保留。")
                            )
                              return;
                            try {
                              await api("/documents/" + d.id, {
                                method: "DELETE",
                              });
                              await onRefresh();
                            } catch (e) {
                              onError((e as Error).message);
                            }
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtered.length && (
          <Empty
            title={search ? "没有找到匹配文档" : "这里还没有文档"}
            description={
              search
                ? "尝试其他关键词或清除筛选。"
                : "上传 PDF、TXT 或 Markdown，开始建立知识库。"
            }
            action={
              <button className="button secondary" onClick={onUpload}>
                上传文档
              </button>
            }
          />
        )}
        <div className="table-footer">
          共 {filtered.length} 份文档{" "}
          <span>公共基准只读 · 个人资料独立管理</span>
        </div>
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
