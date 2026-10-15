"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import type { ExportJob } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; jobs: ExportJob[] };

const FORMAT_LABEL: Record<string, string> = {
  docx: "Word（证据目录 + 时间轴）",
  pdf: "PDF（带页码）",
  zip: "ZIP（文档 + 原始文件）",
};

const STATUS_LABEL: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "生成中",
  COMPLETED: "已完成",
  FAILED: "失败",
};

/** 导出中心: generate, preview, download and delete the evidence bundle. */
export default function ExportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await api.listExports(params.id);
      setState({ kind: "ready", jobs: res.exports });
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

  async function generate(format: string) {
    setBusy(format);
    setNotice(null);
    try {
      await api.createExport(params.id, format);
      setNotice("导出已生成，可以下载。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "导出失败");
    } finally {
      setBusy(null);
    }
  }

  // Downloads must carry the bearer token — a bare <a href> would 401.
  async function download(job: ExportJob) {
    setDownloading(job.id);
    setNotice(null);
    try {
      await api.downloadExport(job.id, `证据包.${job.format}`);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "下载失败");
    } finally {
      setDownloading(null);
    }
  }

  // Preview: fetch the bytes with the token, open a blob URL in a new tab.
  async function view(job: ExportJob) {
    setViewing(job.id);
    setNotice(null);
    try {
      const blob = await api.fetchExportBlob(job.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noreferrer");
      // Revoke after the browser has had time to start rendering.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "预览失败");
    } finally {
      setViewing(null);
    }
  }

  async function remove(job: ExportJob) {
    if (!window.confirm(`确定删除这次「${FORMAT_LABEL[job.format] ?? job.format}」导出吗？`)) return;
    setDeleting(job.id);
    setNotice(null);
    try {
      await api.deleteExport(job.id);
      setNotice("已删除该导出记录。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setDeleting(null);
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">导出中心</h1>
        <button className="btn-ghost" onClick={() => void load()}>
          刷新
        </button>
      </div>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}

      <div className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">生成证据包</h2>
        <p className="text-sm text-slate-500">
          只导出<b>已确认</b>的证据和时间轴事件。编号为「证据1、证据2…」，PDF 页码为「第 X 页 / 共 Y 页」。
        </p>
        <div className="flex flex-wrap gap-2">
          {(["docx", "pdf", "zip"] as const).map((fmt) => (
            <button
              key={fmt}
              className="btn-primary"
              disabled={busy !== null}
              onClick={() => void generate(fmt)}
            >
              {busy === fmt ? "生成中…" : FORMAT_LABEL[fmt]}
            </button>
          ))}
        </div>
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">历史导出</h2>
        {state.jobs.length === 0 ? (
          <div className="empty-state">还没有导出记录。</div>
        ) : (
          <ul className="space-y-2">
            {state.jobs.map((job) => (
              <li key={job.id} className="card flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium">{FORMAT_LABEL[job.format] ?? job.format}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {new Date(job.created_at).toLocaleString("zh-CN")}
                    {job.completed_at
                      ? ` · 完成于 ${new Date(job.completed_at).toLocaleTimeString("zh-CN")}`
                      : ""}
                  </p>
                  {job.error_message && (
                    <p className="mt-1 text-xs text-red-600">{job.error_message}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      job.status === "COMPLETED"
                        ? "bg-emerald-100 text-emerald-700"
                        : job.status === "FAILED"
                          ? "bg-red-100 text-red-700"
                          : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {STATUS_LABEL[job.status] ?? job.status}
                  </span>
                  {job.status === "COMPLETED" && (
                    <>
                      <button
                        className="btn-ghost"
                        disabled={viewing !== null || downloading !== null}
                        onClick={() => void view(job)}
                      >
                        {viewing === job.id ? "打开中…" : "查看"}
                      </button>
                      <button
                        className="btn-ghost"
                        disabled={downloading !== null}
                        onClick={() => void download(job)}
                      >
                        {downloading === job.id ? "下载中…" : "下载"}
                      </button>
                    </>
                  )}
                  <button
                    className="btn-ghost text-red-600"
                    disabled={deleting !== null}
                    onClick={() => void remove(job)}
                  >
                    {deleting === job.id ? "删除中…" : "删除"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
