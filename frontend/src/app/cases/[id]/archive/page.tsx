"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import type { AuditEntry, CaseDetail, CaseProgress } from "@/lib/types";
import { PageHeader, StatusBadge, TaskList } from "@/components/workbench";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CaseDetail; progress: CaseProgress; activity: AuditEntry[] };

/**
 * 案件归档：完成度核对 + 状态切换 + 操作记录。
 * 归档只改变案件状态；删除是单独的、需要二次确认的动作。
 */
export default function ArchivePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [data, progress, audit] = await Promise.all([
        api.getCase(params.id),
        api.getProgress(params.id),
        api.listCaseAudit(params.id, 15),
      ]);
      setState({ kind: "ready", data, progress, activity: audit.items });
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

  async function setStatus(status: "ACTIVE" | "ARCHIVED" | "CLOSED") {
    setBusy(true);
    setNotice(null);
    try {
      await api.updateCase(params.id, { status });
      setNotice("已更新案件状态。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteCase() {
    const name = state.kind === "ready" ? state.data.name : "";
    if (!window.confirm(`永久删除案件「${name}」？软删除后可在审计记录中追溯，但界面将不再显示。`))
      return;
    setBusy(true);
    try {
      await api.deleteCase(params.id);
      router.replace("/cases");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "删除失败");
      setBusy(false);
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

  const { data: c, progress, activity } = state;
  const undone = progress.tasks.filter((t) => !t.done);
  const doneCount = progress.tasks.length - undone.length;

  return (
    <div className="space-y-5">
      <PageHeader
        title="案件归档"
        description="核对材料完成度后归档。归档与删除是不同操作：归档随时可逆，删除为软删除。"
        actions={<StatusBadge status={c.status} />}
      />

      {notice ? (
        <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600" role="status">
          {notice}
        </div>
      ) : null}

      <section className="card">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-600">
            任务完成度：{doneCount} / {progress.tasks.length}
          </span>
          <span className="text-xs text-slate-400">当前阶段：{progress.stage_label}</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-slate-800 transition-all"
            style={{ width: `${Math.round((doneCount / Math.max(progress.tasks.length, 1)) * 100)}%` }}
          />
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-600">全部任务</h2>
        <TaskList caseId={params.id} tasks={progress.tasks} />
      </section>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">案件状态</h2>
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-ghost"
            disabled={busy || c.status === "ACTIVE"}
            onClick={() => void setStatus("ACTIVE")}
          >
            恢复为进行中
          </button>
          <button
            className="btn-primary"
            disabled={busy || c.status === "ARCHIVED"}
            onClick={() => void setStatus("ARCHIVED")}
          >
            归档案件
          </button>
          <button
            className="btn-ghost"
            disabled={busy || c.status === "CLOSED"}
            onClick={() => void setStatus("CLOSED")}
          >
            标记为已结案
          </button>
        </div>
        <p className="text-xs text-slate-400">
          归档后仍可浏览与导出；如需打包原始文件，请到
          <Link className="underline" href={`/cases/${params.id}/export`}>
            导出中心
          </Link>
          生成 ZIP。
        </p>
      </section>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">操作记录</h2>
        {activity.length === 0 ? (
          <div className="text-sm text-slate-400">暂无记录。</div>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {activity.map((entry) => (
              <li key={entry.id} className="flex justify-between py-2">
                <span className="text-slate-700">{entry.action}</span>
                <span className="text-xs text-slate-400">
                  {new Date(entry.created_at).toLocaleString("zh-CN")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card space-y-2 border-rose-100 bg-rose-50">
        <h2 className="text-sm font-semibold text-rose-800">危险操作</h2>
        <p className="text-sm text-rose-700">
          删除案件将使其从列表消失（软删除，可审计追溯）。建议先导出 ZIP 备份。
        </p>
        <button className="btn-ghost border-rose-300 text-rose-700" disabled={busy} onClick={() => void deleteCase()}>
          删除案件
        </button>
      </section>
    </div>
  );
}
