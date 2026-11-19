let token = sessionStorage.getItem("rag.session") || "";
export const setToken = (value: string) => {
  token = value;
  value
    ? sessionStorage.setItem("rag.session", value)
    : sessionStorage.removeItem("rag.session");
};
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", "Bearer " + token);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + path, { ...init, headers });
  if (!response.ok) {
    let message = "请求失败，请稍后重试";
    try {
      message = (await response.json()).message || message;
    } catch {}
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("rag:unauthorized"));
    throw new Error(message);
  }
  return response.json();
}
export async function fileBlob(id: string) {
  const r = await fetch("/api/documents/" + encodeURIComponent(id) + "/file", {
    headers: { Authorization: "Bearer " + token },
  });
  if (!r.ok) throw new Error("文件不存在或不可访问");
  return URL.createObjectURL(await r.blob());
}
export async function streamRun(
  id: string,
  onValue: (value: import("./types").Run) => void,
  signal: AbortSignal,
) {
  const response = await fetch("/api/runs/" + id + "/events", {
    headers: { Authorization: "Bearer " + token },
    signal,
  });
  if (!response.ok || !response.body) throw new Error("实时连接暂不可用");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = block
          .split("\n")
          .filter((x) => x.startsWith("data:"))
          .map((x) => x.slice(5).trimStart())
          .join("\n");
        if (data) onValue(JSON.parse(data));
      }
    }
  } finally {
    reader.releaseLock();
  }
}
