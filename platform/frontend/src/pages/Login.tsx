import { useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  FileText,
  ShieldCheck,
  LoaderCircle,
  Layers,
} from "lucide-react";
import { api, setToken } from "../api";
import type { User } from "../types";
import { Brand } from "../components/ui";

export function Login({
  onLogin,
  onError,
}: {
  onLogin: (u: User) => void;
  onError: (s: string) => void;
}) {
  const [register, setRegister] = useState(false),
    [email, setEmail] = useState("demo@raglab.local"),
    [password, setPassword] = useState("RagLab2026!"),
    [name, setName] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ token: string; user: User }>(
        "/auth/" + (register ? "register" : "login"),
        { method: "POST", body: JSON.stringify({ email, password, name }) },
      );
      setToken(r.token);
      onLogin(r.user);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login">
      <aside className="login-story">
        <Brand />
        <div className="login-copy">
          <span className="eyebrow light">YOUR EVIDENCE. YOUR ANSWERS.</span>
          <h1>
            让每一个答案，
            <br />
            都有据可循。
          </h1>
          <p>
            连接企业文档、智能检索与可验证的回答。
            <br />
            为认真研究的人，构建清晰的知识工作流。
          </p>
          <div className="login-illustration">
            <div className="orbit one" />
            <div className="orbit two" />
            <div className="floating-file f1">
              <FileText />
              <span>
                Annual Report
                <br />
                <small>财报与研究文档</small>
              </span>
            </div>
            <div className="floating-file f2">
              <ShieldCheck />
              <span>
                Evidence grounded
                <br />
                <small>可追溯的证据链</small>
              </span>
            </div>
            <div className="central-node">
              <Layers size={43} />
            </div>
          </div>
        </div>
        <div className="login-footer">
          ENTERPRISE RAG LAB <span>Research with confidence.</span>
        </div>
      </aside>
      <main className="login-form">
        <div className="form-box">
          <span className="eyebrow">你的研究空间</span>
          <h2>{register ? "创建研究账号" : "欢迎回到工作台"}</h2>
          <p>
            {register
              ? "文档、会话与任务按账号独立保存。"
              : "登录后，继续探索你的企业知识库。"}
          </p>
          <form onSubmit={submit}>
            {register && (
              <label>
                你的名字
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={80}
                  placeholder="如何称呼你"
                />
              </label>
            )}
            <label>
              邮箱地址
              <input
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@company.com"
              />
            </label>
            <label>
              密码
              <input
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                minLength={8}
                maxLength={72}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <button className="button primary full" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={17} /> : null}
              {register ? "创建账号" : "进入工作台"}
              <ArrowRight size={17} />
            </button>
          </form>
          <button
            className="text-button login-switch"
            onClick={() => {
              setRegister(!register);
              setEmail("");
              setPassword("");
            }}
          >
            {register ? "已有账号？返回登录" : "还没有账号？创建一个"}
          </button>
          <div className="demo-note">
            <ShieldCheck size={17} />
            <div>
              <strong>本地演示账号</strong>
              <span>demo@raglab.local · RagLab2026!</span>
            </div>
          </div>
        </div>
        <span className="login-bottom">PRIVATE BY DESIGN · EVIDENCE FIRST</span>
      </main>
    </div>
  );
}
