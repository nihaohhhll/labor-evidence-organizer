"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import type { MaterialPackageSnapshot } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; snapshots: MaterialPackageSnapshot[]; total: number };

/**
 * 材料包历史版本列表（9-B §3.3）。历史快照只读：这里只展示与跳转，
 * 不提供任何编辑入口；草稿本身始终在编辑页处理。
 */
export default function MaterialPackageHistoryPage() {
  const params = useParams<{ id: string; pkgId: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [pkg, res] = await Promise.all([
        api.getMaterialPackage(params.pkgId),
        api.listMaterialPackageSnapshots(params.pkgId),
      ]);
      void pkg;
      setState({ kind: "ready", snapshots: res.snapshots, total: res.total });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ kind: "error", message: err instanceof Error ? err.message : "加载失败" });
    }
  }, [params.pkgId, router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [load, router]);

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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">历史版本（{state.total}）</h1>
        <div className="flex gap-2">
          <Link className="btn-ghost" href={`/cases/${params.id}/material-packages/${params.pkgId}/edit`}>
            返回编辑
          </Link>
          <Link className="btn-ghost" href={`/cases/${params.id}/material-packages`}>
            材料包列表
          </Link>
        </div>
      </div>

      <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
        历史快照为只读版本，不会随草稿变化；如需调整内容，请在编辑页修改草稿后创建新的快照。
      </p>

      {state.snapshots.length === 0 ? (
        <div className="empty-state">
          <p>还没有历史快照。</p>
          <p className="mt-1 text-xs text-slate-400">
            在编辑页保存草稿后点击「创建快照」即可归档当前版本。
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {state.snapshots.map((s) => (
            <li key={s.id}>
              <Link
                className="card flex items-center justify-between hover:border-slate-400"
                href={`/cases/${params.id}/material-packages/${params.pkgId}/history/${s.version}`}
              >
                <span className="font-medium">版本 v{s.version}</span>
                <span className="text-xs text-slate-400">
                  条目 {s.content.items?.length ?? 0} ·{" "}
                  {new Date(s.created_at).toLocaleString("zh-CN")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
