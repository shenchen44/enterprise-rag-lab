import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  ArrowUpRight,
  LoaderCircle,
  Square,
  RefreshCw,
} from "lucide-react";
import { api } from "../api";
import type { Run } from "../types";
import { date, active } from "../lib/format";
import { Badge, Empty } from "../components/ui";

export function Runs({
  onError,
  onOpen,
}: {
  onError: (s: string) => void;
  onOpen: (r: Run) => void;
}) {
  const [runs, setRuns] = useState<Run[]>([]),
    [filter, setFilter] = useState("all"),
    [busy, setBusy] = useState(true);
  const load = useCallback(async () => {
    try {
      setRuns(await api<Run[]>("/runs"));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [onError]);
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 3000);
    return () => clearInterval(t);
  }, [load]);
  const filtered = runs.filter(
    (r) =>
      filter === "all" ||
      (filter === "active" ? active(r.status) : r.status === filter),
  );
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">EXECUTION HISTORY</span>
          <h1>每次执行，都有迹可循。</h1>
          <p>查看问答任务的状态、耗时与失败原因。</p>
        </div>
        <button className="button secondary" onClick={() => void load()}>
          <RefreshCw size={15} />
          刷新记录
        </button>
      </div>
      <div className="run-summary">
        <div>
          <span>全部任务</span>
          <strong>{runs.length}</strong>
        </div>
        <div>
          <span>已完成</span>
          <strong>{runs.filter((r) => r.status === "SUCCEEDED").length}</strong>
        </div>
        <div>
          <span>执行中</span>
          <strong>{runs.filter((r) => active(r.status)).length}</strong>
        </div>
        <div>
          <span>失败或中断</span>
          <strong>
            {
              runs.filter(
                (r) => r.status === "FAILED" || r.status === "INTERRUPTED",
              ).length
            }
          </strong>
        </div>
      </div>
      <section className="panel">
        <div className="table-toolbar">
          <div className="tabs">
            {[
              ["all", "全部"],
              ["active", "进行中"],
              ["SUCCEEDED", "已完成"],
              ["FAILED", "失败"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={filter === id ? "active" : ""}
                onClick={() => setFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="muted small-text">每 3 秒更新</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>任务与问题</th>
                <th>模式</th>
                <th>状态</th>
                <th>耗时</th>
                <th>日期</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td>
                    <button className="run-title" onClick={() => onOpen(r)}>
                      <strong>{r.question}</strong>
                      <small>
                        {r.id.slice(0, 8)}
                        {r.error ? " · " + r.error : ""}
                      </small>
                    </button>
                  </td>
                  <td>
                    <span className="source-tag">
                      {r.mode === "live" ? "模型问答" : "证据预览"}
                    </span>
                  </td>
                  <td>
                    <Badge status={r.status} />
                  </td>
                  <td>
                    {r.latencyMs ? (r.latencyMs / 1000).toFixed(1) + "s" : "—"}
                  </td>
                  <td>{date(r.createdAt)}</td>
                  <td>
                    <div className="row-actions">
                      {active(r.status) && (
                        <button
                          className="icon-button"
                          title="停止任务"
                          aria-label="停止任务"
                          onClick={async () => {
                            try {
                              await api("/runs/" + r.id + "/cancel", {
                                method: "POST",
                              });
                              await load();
                            } catch (e) {
                              onError((e as Error).message);
                            }
                          }}
                        >
                          <Square size={15} />
                        </button>
                      )}
                      <button
                        className="icon-button"
                        title="打开会话"
                        aria-label="打开会话"
                        onClick={() => onOpen(r)}
                      >
                        <ArrowUpRight size={17} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!filtered.length && !busy && (
          <Empty
            icon={Activity}
            title="还没有任务记录"
            description="发起一次问答，执行状态和结果会自动保存在这里。"
          />
        )}
        {busy && (
          <div className="page-loading">
            <LoaderCircle className="spin" />
            正在载入任务
          </div>
        )}
        <div className="table-footer">
          显示最近 100 个任务 <span>取消为尽力传递 · 中断结果需核实后重试</span>
        </div>
      </section>
    </div>
  );
}
