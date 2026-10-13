"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import { PACKAGE_STATUS_LABELS } from "@/lib/material-package-ui";
import type { MaterialPackageList } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: MaterialPackageList };

const STATUS_TONE: Record<string, string> = {
  DRAFT: "bg-amber-100 text-amber-700",
  PUBLISHED: "bg-emerald-100 text-emerald-700",
  ARCHIVED: "bg-slate-100 text-slate-600",
};

/** 材料包列表：案件内的入口页（9-B §3.1，9-C 增发布/删除/截断提示）。 */
export default function MaterialPackageListPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      // limit=100: the endpoint defaults to 20, silently truncating longer lists.
      const data = await api.listMaterialPackages(params.id, 100);
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
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [load, router]);

  async function publish(id: string, name: string) {
    if (!window.confirm(`发布「${name}」？发布只是状态标记，发布后仍可继续编辑条目。`)) return;
    setBusyId(id);
    setNotice(null);
    try {
      await api.updateMaterialPackage(id, { status: "PUBLISHED" });
      setNotice(`「${name}」已发布。`);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "发布失败");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: string, name: string) {
    if (!window.confirm(`删除草稿「${name}」？该操作不可撤销。`)) return;
    setBusyId(id);
    setNotice(null);
    try {
      await api.deleteMaterialPackage(id);
      setNotice(`「${name}」已删除。`);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "删除失败");
      await load();
    } finally {
      setBusyId(null);
    }
  }

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

  const packages = state.data.items;
  const truncated = state.data.total > packages.length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">仲裁材料包</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => void load()}>
            刷新
          </button>
          <Link className="btn-primary" href={`/cases/${params.id}/material-packages/new`}>
            新建材料包
          </Link>
        </div>
      </div>

      <p className="text-xs text-slate-400">
        材料包只是对现有证据的编排，不会修改或删除任何原始证据。
      </p>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}

      {truncated && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700" role="status">
          共 {state.data.total} 个材料包，当前一次最多显示 {packages.length} 个。请按案件归档或分批整理。
        </p>
      )}

      {packages.length === 0 ? (
        <div className="empty-state">
          <p>还没有材料包。</p>
          <p className="mt-2 text-sm text-slate-500">
            材料包用于把案件证据按仲裁提交顺序编排成目录，创建第一个材料包开始整理。
          </p>
          <Link className="btn-primary mt-4 inline-block" href={`/cases/${params.id}/material-packages/new`}>
            创建第一个材料包
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {packages.map((p) => (
            <li key={p.id} className="card flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{p.name}</p>
                <p className="mt-0.5 text-xs text-slate-400">
                  草稿版本 v{p.draft_version} · 条目 {p.item_count} · 历史快照 {p.snapshot_count} ·
                  更新于 {new Date(p.updated_at).toLocaleString("zh-CN")}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs ${STATUS_TONE[p.status] ?? "bg-slate-100"}`}>
                  {PACKAGE_STATUS_LABELS[p.status] ?? p.status}
                </span>
                {p.status === "DRAFT" && (
                  <button
                    className="text-sm text-emerald-700 underline"
                    disabled={busyId === p.id}
                    onClick={() => void publish(p.id, p.name)}
                  >
                    发布
                  </button>
                )}
                <Link className="text-sm text-slate-600 underline" href={`/cases/${params.id}/material-packages/${p.id}/edit`}>
                  {p.status === "ARCHIVED" ? "查看" : "编辑"}
                </Link>
                <Link className="text-sm text-slate-500 underline" href={`/cases/${params.id}/material-packages/${p.id}/export`}>
                  导出成卷
                </Link>
                <Link className="text-sm text-slate-500 underline" href={`/cases/${params.id}/material-packages/${p.id}/history`}>
                  历史版本
                </Link>
                {p.status === "DRAFT" && p.snapshot_count === 0 && (
                  <button
                    className="text-sm text-red-600 underline"
                    disabled={busyId === p.id}
                    onClick={() => void remove(p.id, p.name)}
                  >
                    {busyId === p.id ? "删除中…" : "删除"}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
