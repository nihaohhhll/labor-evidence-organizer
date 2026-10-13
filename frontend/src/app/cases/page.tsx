"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, api, getToken, setToken } from "@/lib/api";
import type { CasePage } from "@/lib/types";

/** Loading / empty / error states are required for every view (02_USER_STORIES DoD). */
type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; page: CasePage };

export default function CasesPage() {
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const page = await api.listCases();
      setState({ kind: "ready", page });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setToken(null);
        router.replace("/login");
        return;
      }
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "加载失败",
      });
    }
  }, [router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [load, router]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">我的案件</h1>
        <Link href="/cases/new" className="btn-primary">
          新建案件
        </Link>
      </div>

      {state.kind === "loading" && <div className="empty-state">加载中…</div>}

      {state.kind === "error" && (
        <div className="empty-state" role="alert">
          <p>{state.message}</p>
          <button className="btn-ghost mt-3" onClick={() => void load()}>
            重试
          </button>
        </div>
      )}

      {state.kind === "ready" && state.page.items.length === 0 && (
        <div className="empty-state">
          还没有案件。创建一个案件，把合同、聊天截图、工资记录等资料拖进来，AI
          会先帮你整理。
        </div>
      )}

      {state.kind === "ready" && state.page.items.length > 0 && (
        <ul className="space-y-3">
          {state.page.items.map((c) => (
            <li key={c.id}>
              <Link href={`/cases/${c.id}`} className="card block hover:border-slate-400">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{c.name}</span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {c.status}
                  </span>
                </div>
                {c.description && (
                  <p className="mt-1 line-clamp-2 text-sm text-slate-500">{c.description}</p>
                )}
                <p className="mt-2 text-xs text-slate-400">
                  创建于 {new Date(c.created_at).toLocaleString("zh-CN")}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
