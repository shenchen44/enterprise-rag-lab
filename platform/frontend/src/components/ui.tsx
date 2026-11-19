import { useEffect } from "react";
import type { ReactNode } from "react";
import { Library, X, Layers, FolderOpen } from "lucide-react";
import { statusText } from "../lib/format";

export function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status.toLowerCase()}>
      <i />
      {statusText[status] || status}
    </span>
  );
}

export function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className={"brand " + (small ? "small" : "")}>
      <span className="brand-mark">
        <Layers size={21} />
      </span>
      <div>
        <strong>
          Enterprise RAG<span>LAB</span>
        </strong>
        {!small && <small>从文档到可信答案</small>}
      </div>
    </div>
  );
}

export function Empty({
  icon: Icon = FolderOpen,
  title,
  description,
  action,
}: {
  icon?: typeof Library;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon size={26} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [onClose]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={"modal " + (wide ? "wide" : "")}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <X size={19} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

export function Metric({
  icon: Icon,
  label,
  value,
  detail,
  sub,
}: {
  icon: typeof Library;
  label: string;
  value: string;
  detail: string;
  sub: string;
}) {
  return (
    <section className="metric">
      <div className="metric-top">
        <span>{label}</span>
        <Icon size={17} />
      </div>
      <div className="metric-value">{value}</div>
      <p>{detail}</p>
      <small>{sub}</small>
    </section>
  );
}
