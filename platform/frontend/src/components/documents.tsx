import { useState, useEffect, useRef } from "react";
import {
  FileText,
  Download,
  Upload,
  X,
  ShieldCheck,
  LoaderCircle,
  ExternalLink,
} from "lucide-react";
import { api, fileBlob } from "../api";
import type { Document, Citation } from "../types";
import { bytes } from "../lib/format";
import { Modal } from "../components/ui";

export function UploadModal({
  onClose,
  onDone,
  onError,
}: {
  onClose: () => void;
  onDone: () => void;
  onError: (s: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [drag, setDrag] = useState(false),
    input = useRef<HTMLInputElement>(null);
  function choose(f: File | undefined) {
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) {
      onError("文件不能超过 20 MB");
      return;
    }
    if (!/\.(pdf|txt|md)$/i.test(f.name)) {
      onError("请选择 PDF、TXT 或 Markdown 文件");
      return;
    }
    setFile(f);
  }
  async function upload() {
    if (!file) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      await api("/documents", { method: "POST", body });
      onDone();
      onClose();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="添加研究文档"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="upload-body">
        <button
          className={"dropzone " + (drag ? "drag" : "")}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            choose(e.dataTransfer.files[0]);
          }}
        >
          <span className="upload-circle">
            <Upload size={25} />
          </span>
          <strong>{file ? file.name : "点击选择，或将文件拖到这里"}</strong>
          <p>
            {file ? bytes(file.size) : "支持 PDF、TXT、Markdown · 最大 20 MB"}
          </p>
        </button>
        <input
          ref={input}
          type="file"
          hidden
          accept=".pdf,.txt,.md"
          onChange={(e) => choose(e.target.files?.[0])}
        />
        <div className="upload-info">
          <ShieldCheck size={17} />
          <p>
            文档仅对你的账号可见。上传后自动提取文字并建立检索证据；扫描 PDF
            请先进行 OCR。
          </p>
        </div>
        <div className="modal-actions">
          <button
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            取消
          </button>
          <button
            className="button primary"
            disabled={!file || busy}
            onClick={upload}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Upload size={16} />
            )}
            上传并解析
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function DocumentModal({
  document: d,
  onClose,
  onError,
  initialPage,
}: {
  document: Document;
  onClose: () => void;
  onError: (s: string) => void;
  initialPage?: number;
}) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let current = "";
    let stop = false;
    fileBlob(d.id)
      .then((u) => {
        current = u;
        if (!stop) setUrl(u);
        else URL.revokeObjectURL(u);
      })
      .catch((e) => onError(e.message));
    return () => {
      stop = true;
      if (current) URL.revokeObjectURL(current);
    };
  }, [d.id, onError]);
  return (
    <Modal title={d.title} onClose={onClose} wide>
      <div className="document-preview-head">
        <span>
          {initialPage
            ? `定位到第 ${initialPage} 页`
            : `${d.pages} 页 · ${bytes(d.bytes)}`}
        </span>
        {url && (
          <a
            className="button secondary small"
            download={d.fileName}
            href={url}
          >
            <Download size={14} />
            下载原文件
          </a>
        )}
      </div>
      {url ? (
        <iframe
          title={d.fileName}
          src={`${url}#page=${initialPage || 1}&view=FitH`}
          className="pdf-preview"
        />
      ) : (
        <div className="preview-loading">
          <LoaderCircle className="spin" />
          正在读取文档
        </div>
      )}
    </Modal>
  );
}

export function CitationPanel({
  citation: c,
  onClose,
  onError,
}: {
  citation: Citation;
  onClose: () => void;
  onError: (s: string) => void;
}) {
  const [preview, setPreview] = useState(false);
  return (
    <div
      className="citation-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className="citation-panel">
        <div className="modal-head">
          <span className="eyebrow">SOURCE EVIDENCE</span>
          <button
            className="icon-button"
            aria-label="关闭引用"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </div>
        <span className="file-icon">
          <FileText size={25} />
        </span>
        <h2>{c.fileName}</h2>
        <div className="citation-meta">
          <span>第 {c.page} 页</span>
          <span>检索得分 {c.score}</span>
        </div>
        <h3>引用原文</h3>
        <pre>{c.text}</pre>
        <p className="muted">检索得分用于排序，不代表答案正确性的概率。</p>
        <button className="button primary" onClick={() => setPreview(true)}>
          <ExternalLink size={16} />
          查看原文件
        </button>
        {preview && (
          <DocumentModal
            document={{
              id: c.documentId,
              title: c.fileName,
              fileName: c.fileName,
              pages: c.page,
              bytes: 0,
              kind: "",
              status: "READY",
              chunks: 0,
              createdAt: "",
            }}
            initialPage={c.page}
            onClose={() => setPreview(false)}
            onError={onError}
          />
        )}
      </aside>
    </div>
  );
}
