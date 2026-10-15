"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CaseDetail };

/** Case dashboard: counts + quick status (navigation lives in the sidebar layout). */
export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await api.getCase(params.id);
      setState({ kind: "ready", data });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ kind: "error", message: err instanceof Error ? err.message : "加载失败" });
    }
  }, [params.id, router]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") return <div className="empty-state">加载中…</div>;
  if (state.kind === "error")
    return (
      <div className="empty-state" role="alert">
        <p>{state.message}</p>
        <button className="btn-ghost mt-3" onClick={() => void load()}>
          重试
        </button>
      </div>
    );

  const c = state.data;
  const stats = [
    { label: "文件", value: c.file_count },
    { label: "证据", value: c.evidence_count },
    { label: "时间轴事件", value: c.event_count },
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{c.name}</h1>
          {c.description && <p className="mt-1 text-sm text-slate-500">{c.description}</p>}
        </div>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{c.status}</span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="card text-center">
            <div className="text-2xl font-semibold">{s.value}</div>
            <div className="text-sm text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      <p className="text-xs text-slate-400">
        更新于 {new Date(c.updated_at).toLocaleString("zh-CN")}
      </p>
    </div>
  );
}
