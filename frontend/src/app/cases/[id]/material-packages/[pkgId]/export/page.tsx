"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import type {
  EvidenceGapResult,
  ExportJob,
  MaterialPackageDetail,
  MaterialPackageSnapshot,
} from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      pkg: MaterialPackageDetail;
      snapshots: MaterialPackageSnapshot[];
      jobs: ExportJob[];
      gap: EvidenceGapResult | null;
    };

const FORMAT_LABEL: Record<string, string> = {
  docx: "Word 卷宗（docx）",
  pdf: "PDF 卷宗（pdf）",
};

const STATUS_LABEL: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "生成中",
  COMPLETED: "已完成",
  FAILED: "失败",
};

/**
 * 材料包成卷导出页（9-C §3）：从不可变快照渲染 PDF/DOCX。
 * 正文来自快照绑定的原始证据内容；可选附录为中性的材料完整性提示。
 */
export default function MaterialPackageExportPage() {
  const params = useParams<{ id: string; pkgId: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [format, setFormat] = useState("docx");
  const [snapshotVersion, setSnapshotVersion] = useState<number | "latest">("latest");
  const [includeAppendix, setIncludeAppendix] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    setError(null);
    try {
      const [pkg, snaps, exportsRes] = await Promise.all([
        api.getMaterialPackage(params.pkgId),
        api.listMaterialPackageSnapshots(params.pkgId),
        api.listMaterialPackageExports(params.pkgId, 100),
      ]);
      // A3 结果可选：404 = 尚未运行分析，不影响导出本身。
      let gap: EvidenceGapResult | null = null;
      try {
        gap = await api.getLatestEvidenceGaps(params.id);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) gap = null;
        else if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
      }
      setState({
        kind: "ready",
        pkg,
        snapshots: snaps.snapshots,
        jobs: exportsRes.exports,
        gap,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ kind: "error", message: err instanceof Error ? err.message : "加载失败" });
    }
  }, [params.id, params.pkgId, router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [load, router]);

  async function generate() {
    if (state.kind !== "ready") return;
    setSubmitting(true);
    setNotice(null);
    setError(null);
    try {
      const job = await api.createMaterialPackageExport(params.pkgId, {
        format,
        ...(snapshotVersion !== "latest" ? { snapshot_version: snapshotVersion } : {}),
        include_gap_appendix: includeAppendix,
      });
      if (job.status === "COMPLETED") {
        setNotice(
          `已从快照 v${job.snapshot_version ?? "?"} 生成 ${FORMAT_LABEL[job.format] ?? job.format}，可以下载。`,
        );
      } else if (job.status === "FAILED") {
        setError(job.error_message ?? "生成失败");
      } else {
        setNotice("导出任务已提交。");
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "导出失败，请重试");
    } finally {
      setSubmitting(false);
    }
  }

  async function download(job: ExportJob) {
    setDownloading(job.id);
    setError(null);
    try {
      const name = state.kind === "ready" ? `材料包-${state.pkg.name}.${job.format}` : "package";
      await api.downloadExport(job.id, name);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "下载失败");
    } finally {
      setDownloading(null);
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

  const { pkg, snapshots, jobs, gap } = state;
  const gapAvailable = gap !== null && gap.status === "SUCCESS";
  const hasSnapshots = snapshots.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">导出成卷：{pkg.name}</h1>
          <p className="mt-0.5 text-xs text-slate-400">
            从快照渲染 PDF/DOCX 卷宗；正文嵌入各条目的原始证据内容，转换失败会在文中显式标注。
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            className="btn-ghost"
            href={`/cases/${params.id}/material-packages/${params.pkgId}/edit`}
          >
            返回编辑
          </Link>
          <button className="btn-ghost" onClick={() => void load()}>
            刷新
          </button>
        </div>
      </div>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">生成材料包卷宗</h2>

        {!hasSnapshots ? (
          <p className="rounded bg-amber-50 px-2 py-1 text-sm text-amber-700">
            尚无快照。请先在编辑页保存草稿并创建快照后再导出（快照保证导出内容不可变）。
          </p>
        ) : (
          <>
            <div className="space-y-1">
              <span className="text-sm text-slate-600">格式</span>
              <div className="flex flex-wrap gap-3">
                {(["docx", "pdf"] as const).map((fmt) => (
                  <label key={fmt} className="flex cursor-pointer items-center gap-1 text-sm">
                    <input
                      type="radio"
                      name="format"
                      value={fmt}
                      checked={format === fmt}
                      onChange={() => setFormat(fmt)}
                    />
                    {FORMAT_LABEL[fmt]}
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-sm text-slate-600" htmlFor="snapshot-select">
                快照版本
              </label>
              <select
                id="snapshot-select"
                className="input w-full max-w-sm"
                value={String(snapshotVersion)}
                onChange={(e) =>
                  setSnapshotVersion(
                    e.target.value === "latest" ? "latest" : Number(e.target.value),
                  )
                }
              >
                <option value="latest">
                  最新快照（v{snapshots[0]?.version}）
                </option>
                {snapshots.map((s) => (
                  <option key={s.id} value={s.version}>
                    快照 v{s.version}（{new Date(s.created_at).toLocaleString("zh-CN")}）
                  </option>
                ))}
              </select>
            </div>

            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={includeAppendix}
                disabled={!gapAvailable}
                onChange={(e) => setIncludeAppendix(e.target.checked)}
              />
              <span>
                附录：材料完整性提示（中性参考，不输出审核状态）
                {!gapAvailable && (
                  <span className="block text-xs text-slate-400">
                    尚无可用的材料缺口分析结果，请先在案件工具中运行「材料缺口分析」。
                  </span>
                )}
              </span>
            </label>

            <button
              className="btn-primary"
              disabled={submitting}
              onClick={() => void generate()}
            >
              {submitting ? "生成中…" : "生成卷宗"}
            </button>
          </>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">导出记录</h2>
        {jobs.length === 0 ? (
          <div className="empty-state">还没有该材料包的导出记录。</div>
        ) : (
          <ul className="space-y-2">
            {jobs.map((job) => (
              <li key={job.id} className="card flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    {FORMAT_LABEL[job.format] ?? job.format}
                    {job.snapshot_version ? ` · 快照 v${job.snapshot_version}` : ""}
                    {job.include_gap_appendix ? " · 含完整性附录" : ""}
                  </p>
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
                    <button
                      className="btn-ghost"
                      disabled={downloading !== null}
                      onClick={() => void download(job)}
                    >
                      {downloading === job.id ? "下载中…" : "下载"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
