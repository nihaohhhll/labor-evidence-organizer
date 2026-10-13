"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import { REVIEW_LABELS, SOURCE_STATUS_LABELS } from "@/lib/material-package-ui";
import { useFilePreview } from "@/lib/file-preview";
import type { MaterialPackageSnapshot, MaterialPackageSnapshotItem } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; snapshot: MaterialPackageSnapshot };

/** 单条快照条目的只读预览面板（来源异常必须显式展示，不静默替换）。 */
function SourcePanel({ item }: { item: MaterialPackageSnapshotItem }) {
  const preview = useFilePreview(item.source_status === "OK" ? item.source_file_id : null);

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          证据{item.display_number}
        </span>
        <span
          className={`text-xs ${
            item.source_status === "MISSING" ? "text-red-600" : "text-slate-400"
          }`}
        >
          {SOURCE_STATUS_LABELS[item.source_status ?? "OK"] ?? item.source_status}
        </span>
      </div>
      <p className="text-sm">{item.display_name}</p>
      <p className="text-xs text-slate-500">
        {item.evidence_title ?? "（来源证据已删除）"}
        {item.evidence_category ? ` · ${item.evidence_category}` : ""}
        {" · "}
        {REVIEW_LABELS[item.review_status as keyof typeof REVIEW_LABELS] ?? item.review_status}
      </p>
      {item.proof_purpose && (
        <p className="whitespace-pre-wrap text-xs text-slate-600">
          <span className="text-slate-400">拟证明事项：</span>
          {item.proof_purpose}
        </p>
      )}
      {item.source_status === "MISSING" ? (
        <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-700" role="alert">
          来源文件/证据已不可用，无法查看原始材料（不会以其他文件替代）。
        </p>
      ) : item.source_status === "CHANGED" ? (
        <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
          来源证据在快照创建后已被修改，下方为当前最新原始文件。
        </p>
      ) : null}
      {preview.kind === "loading" && <p className="text-xs text-slate-400">原始文件加载中…</p>}
      {preview.kind === "error" && (
        <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-700" role="alert">
          来源文件不可用：{preview.message}
        </p>
      )}
      {preview.kind === "ready" && (
        <a
          className="inline-block text-xs text-slate-600 underline"
          href={preview.url}
          target="_blank"
          rel="noreferrer"
        >
          在新窗口打开原始文件
        </a>
      )}
    </div>
  );
}

/**
 * 历史快照只读详情（9-B §3.3）：
 * - 展示条目、顺序、编号、拟证明事项与审核状态；
 * - 无任何编辑/保存控件；快照不能通过草稿编辑接口修改；
 * - 来源证据的访问仍走 /files/{id}/content 的权限校验。
 */
export default function MaterialPackageSnapshotDetailPage() {
  const params = useParams<{ id: string; pkgId: string; version: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [selected, setSelected] = useState<number>(0);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const snapshot = await api.getMaterialPackageSnapshot(params.pkgId, Number(params.version));
      setState({ kind: "ready", snapshot });
      setSelected(0);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ kind: "error", message: err instanceof Error ? err.message : "加载失败" });
    }
  }, [params.pkgId, params.version, router]);

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

  const { snapshot } = state;
  const items = snapshot.content.items ?? [];
  const active = items[Math.min(selected, Math.max(items.length - 1, 0))] ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">历史版本 v{snapshot.version}</h1>
          <p className="mt-0.5 text-xs text-slate-400">
            只读快照 · 创建于 {new Date(snapshot.created_at).toLocaleString("zh-CN")} ·{" "}
            归档时草稿版本 v{snapshot.draft_version_captured}
          </p>
        </div>
        <div className="flex gap-2">
          <Link className="btn-ghost" href={`/cases/${params.id}/material-packages/${params.pkgId}/history`}>
            版本列表
          </Link>
          <Link className="btn-ghost" href={`/cases/${params.id}/material-packages/${params.pkgId}/edit`}>
            返回编辑
          </Link>
        </div>
      </div>

      <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
        本页内容为创建快照时的归档数据，不会随草稿变化；此处不提供编辑操作。
      </p>

      {items.length === 0 ? (
        <div className="empty-state">该快照没有条目。</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="card space-y-2">
            <h2 className="font-medium">条目（{items.length}）</h2>
            <ul className="space-y-1">
              {items.map((it, idx) => (
                <li key={it.item_id}>
                  <button
                    className={`w-full rounded px-2 py-1 text-left text-sm hover:bg-slate-50 ${
                      idx === selected ? "bg-slate-100 font-medium" : ""
                    }`}
                    onClick={() => setSelected(idx)}
                  >
                    <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                      {it.display_number}
                    </span>
                    {it.display_name}
                    <span className="ml-2 text-xs text-slate-400">
                      {REVIEW_LABELS[it.review_status as keyof typeof REVIEW_LABELS] ?? it.review_status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="card space-y-2">
            <h2 className="font-medium">条目详情与原始证据</h2>
            {active ? (
              <SourcePanel item={active} />
            ) : (
              <p className="text-sm text-slate-400">请选择左侧条目。</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
