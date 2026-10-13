"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, setToken } from "@/lib/api";

type Mode = "login" | "register";

/** Shared login / register form. */
export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res =
        mode === "login"
          ? await api.login({ email, password })
          : await api.register({ email, password });
      setToken(res.access_token);
      router.replace("/cases");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-4 text-xl font-semibold">{mode === "login" ? "登录" : "注册"}</h1>
      <form onSubmit={onSubmit} className="card space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">邮箱</span>
          <input
            className="input"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">密码</span>
          <input
            className="input"
            type="password"
            required
            minLength={mode === "register" ? 8 : 1}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <button className="btn-primary w-full" type="submit" disabled={busy}>
          {busy ? "提交中…" : mode === "login" ? "登录" : "注册"}
        </button>

        <button
          type="button"
          className="w-full text-center text-sm text-slate-500 underline"
          onClick={() => {
            setError(null);
            setMode(mode === "login" ? "register" : "login");
          }}
        >
          {mode === "login" ? "还没有账号？去注册" : "已有账号？去登录"}
        </button>
      </form>
    </div>
  );
}
