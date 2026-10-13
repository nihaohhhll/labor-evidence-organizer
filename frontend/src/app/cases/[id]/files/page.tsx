"use client";

import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import type { CaseFile, CaseFileList, UploadResult } from "@/lib/types";

/** Browser FileList needs a distinct name from our API's CaseFileList. */
type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CaseFileList };

const STATUS_LABEL: Record<string, string> = {
  UPLOADED: "已上传",
  QUEUED: "排队中",
  PROCESSING: "解析中",
  REVIEW_REQUIRED: "待确认",
  COMPLETED: "已完成",
  FAILED: "失败",
};

const STATUS_TONE: Record<string, string> = {
  UPLOADED: "bg-slate-100 text-slate-600",
  QUEUED: "bg-sky-100 text-sky-700",
  PROCESSING: "bg-amber-100 text-amber-700",
  REVIEW_REQUIRED: "bg-orange-100 text-orange-700",
  COMPLETED: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-red-100 text-red-700",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 资料库: batch upload, status list, preview, retry and delete. */
export default function CaseFilesPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await api.listFiles(params.id);
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

  async function handleFiles(list: globalThis.FileList | null) {
    if (!list || list.length === 0) return;
    setUploading(true);
    setNotice(null);
    try {
      const chosen: globalThis.File[] = Array.from(list);
      const result: UploadResult = await api.uploadFiles(params.id, chosen);
      const skipped = result.skipped
        .map((s) => `${s.filename}：${s.reason}`)
        .join("；");
      setNotice(
        `成功 ${result.files.length} 个` + (skipped ? `，跳过 ${result.skipped.length} 个（${skipped}）` : ""),
      );
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    void handleFiles(e.target.files);
  }

  async function onAnalyzeAll() {
    setAnalyzing(true);
    setNotice(null);
    try {
      const res = await api.analyzeCase(params.id);
      setNotice(`已解析 ${res.analyzed} 个文件。`);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "解析失败");
    } finally {
      setAnalyzing(false);
    }
  }

  async function onRetry(f: CaseFile) {
    try {
      await api.retryFile(f.id);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "重试失败");
    }
  }

  async function onDelete(f: CaseFile) {
    if (!window.confirm(`确定删除「${f.original_filename}」吗？（软删除，原件保留）`)) return;
    try {
      await api.deleteFile(f.id);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "删除失败");
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

  const files = state.data.files;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">资料库</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => void load()}>
            刷新
          </button>
          <button
            className="btn-primary"
            onClick={() => void onAnalyzeAll()}
            disabled={analyzing || files.length === 0}
          >
            {analyzing ? "解析中…" : "全部解析"}
          </button>
        </div>
      </div>

      {/* Drop zone */}
      <div
        className={`empty-state cursor-pointer ${dragging ? "border-slate-900 bg-slate-100" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void handleFiles(e.dataTransfer.files);
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        {uploading ? (
          "上传中…"
        ) : (
          <>
            把合同、聊天截图、工资记录等资料拖进来，AI 会先帮你整理。
            <p className="mt-2 text-xs text-slate-400">
              支持 PNG / JPG / PDF / DOCX / TXT，单个文件不超过 25 MB
            </p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          accept=".png,.jpg,.jpeg,.pdf,.docx,.txt"
          onChange={onInputChange}
        />
      </div>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}

      {files.length === 0 ? (
        <div className="empty-state">还没有资料。</div>
      ) : (
        <ul className="space-y-2">
          {files.map((f) => (
            <li key={f.id} className="card flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{f.original_filename}</p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {formatSize(f.size)} · SHA-256 {f.sha256.slice(0, 12)}…
                </p>
                {f.error_message && (
                  <p className="mt-1 text-xs text-red-600">{f.error_message}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className={`rounded px-2 py-0.5 text-xs ${STATUS_TONE[f.status] ?? "bg-slate-100"}`}
                >
                  {STATUS_LABEL[f.status] ?? f.status}
                </span>
                <a
                  className="text-sm text-slate-500 underline"
                  href={api.fileContentUrl(f.id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看原始材料
                </a>
                <button className="text-sm text-slate-600 underline" onClick={() => void onRetry(f)}>
                  重试
                </button>
                <button
                  className="text-sm text-red-600 underline"
                  onClick={() => void onDelete(f)}
                >
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
