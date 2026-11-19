export const percent = (n: number | null | undefined) =>
  n == null ? "—" : (n * 100).toFixed(1) + "%";
export const bytes = (n: number) =>
  n > 1048576
    ? (n / 1048576).toFixed(1) + " MB"
    : (n / 1024).toFixed(0) + " KB";
export const date = (s: string) =>
  new Date(s).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
export const active = (s: string) => s === "RUNNING" || s === "QUEUED";
export const statusText: Record<string, string> = {
  READY: "已就绪",
  PROCESSING: "解析中",
  FAILED: "执行失败",
  SUCCEEDED: "已完成",
  RUNNING: "执行中",
  QUEUED: "排队中",
  CANCELLED: "已取消",
  INTERRUPTED: "已中断",
};
