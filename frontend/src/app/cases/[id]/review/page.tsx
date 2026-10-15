"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import type { EvidenceRow, ReviewItem } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: ReviewItem[]; evidence: EvidenceRow[] };

const FIELD_LABEL: Record<string, string> = {
  summary: "内容摘要",
  proof_purpose: "证明目的",
  category: "分类",
  title: "证据名称",
};

function valueText(v: Record<string, string | null> | null, field: string): string {
  if (!v) return "（无）";
  const raw = v[field];
  return raw === null || raw === undefined || raw === "" ? "（无）" : String(raw);
}

/**
 * 审核工作台 (docs/09 FRONTEND_SPEC).
 *
 * The original file is rendered as its own full-width section, deliberately
 * kept out of the evidence-list container below it. The AI value and the
 * user's value are always shown side by side so a human can see exactly what
 * they are changing.
 */
export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const listRef = useRef<HTMLElement | null>(null);

  // When the selected original file changes, scroll the evidence list so the
  // first item belonging to that file sits near the middle of the viewport.
  useEffect(() => {
    if (!activeFileId || !listRef.current) return;
    const container = listRef.current;
    const card = container.querySelector<HTMLElement>(`[data-file-id="${activeFileId}"]`);
    if (!card) return;
    const containerRect = container.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const delta =
      cardRect.top - containerRect.top - (container.clientHeight - cardRect.height) / 2;
    container.scrollTo({ top: container.scrollTop + delta, behavior: "smooth" });
  }, [activeFileId]);

  // Fetch the original with the bearer token and swap the iframe src to a
  // blob URL — a bare <iframe src="/files/..."> cannot carry Authorization.
  useEffect(() => {
    if (!activeFileId) {
      setPreviewUrl(null);
      return;
    }
    let cancelled = false;
    let url: string | null = null;
    api
      .fetchFileContent(activeFileId)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setPreviewUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPreviewUrl(null);
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [activeFileId]);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [items, evidence] = await Promise.all([
        api.listReviewItems(params.id),
        api.listEvidence(params.id),
      ]);
      setState({ kind: "ready", items: items.items, evidence: evidence.evidence });
      const first = evidence.evidence.find((e) => e.source_file_id);
      setActiveFileId((prev) => prev ?? first?.source_file_id ?? null);
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

  async function confirmItem(item: ReviewItem) {
    setNotice(null);
    const typed = drafts[item.id];
    // No edit typed => keep the AI's suggestion; an empty box clears the field.
    const payload: Record<string, string | null> =
      typed !== undefined
        ? { [item.field_name]: typed === "" ? null : typed }
        : (item.ai_value ?? {});
    try {
      if (typed !== undefined) await api.saveReviewValue(item.id, payload);
      await api.confirmReviewItem(item.id);
      setNotice(`已确认「${FIELD_LABEL[item.field_name] ?? item.field_name}」。`);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "确认失败");
    }
  }

  async function discardItem(item: ReviewItem) {
    try {
      await api.discardReviewItem(item.id);
      setNotice("已忽略该建议。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "操作失败");
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

  const sourceFiles = state.evidence
    .map((e) => e.source_file_id)
    .filter((v): v is string => Boolean(v));

  // One card per evidence: group the pending field suggestions by entity.
  const grouped = new Map<string, ReviewItem[]>();
  for (const item of state.items) {
    const list = grouped.get(item.entity_id) ?? [];
    list.push(item);
    grouped.set(item.entity_id, list);
  }

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">AI 审核工作台</h1>
        <button className="btn-ghost" onClick={() => void load()}>
          刷新
        </button>
      </div>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}

      {state.items.length === 0 ? (
        <div className="empty-state">没有待确认的 AI 建议。</div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[24rem_1fr] gap-4">
          {/* Original material — fixed left column, outside the evidence list */}
          <section className="card self-start">
            <h2 className="mb-2 text-sm font-semibold text-slate-600">原始材料</h2>
            {activeFileId ? (
              <>
                {previewUrl ? (
                  <iframe
                    title="原始材料"
                    src={previewUrl}
                    className="h-96 w-full rounded border border-slate-200"
                  />
                ) : (
                  <p className="text-sm text-slate-500">加载预览中…</p>
                )}
                <div className="mt-2 flex items-center justify-between">
                  <button
                    className="inline-block text-sm text-slate-500 underline"
                    onClick={() => {
                      if (previewUrl) window.open(previewUrl, "_blank", "noreferrer");
                    }}
                    disabled={!previewUrl}
                  >
                    在新标签打开
                  </button>
                  {sourceFiles.length > 1 && (
                    <select
                      className="input w-auto"
                      value={activeFileId ?? ""}
                      onChange={(e) => setActiveFileId(e.target.value)}
                    >
                      {sourceFiles.map((fid) => (
                        <option key={fid} value={fid}>
                          文件 {fid.slice(0, 8)}…
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">没有可预览的原始材料。</p>
            )}
          </section>

          {/* Evidence list — right column, scrolls independently */}
          <section ref={listRef} className="min-h-0 space-y-3 overflow-y-auto pr-1">
            <h2 className="text-sm font-semibold text-slate-600">AI 结果与人工修改</h2>
            {[...grouped.entries()].map(([entityId, items]) => {
              const evidence = state.evidence.find((e) => e.id === entityId);
              return (
                <article
                  key={entityId}
                  className="card"
                  data-file-id={evidence?.source_file_id ?? ""}
                >
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <p className="text-sm font-medium">
                      {evidence ? `证据${evidence.evidence_number}` : "未知证据"}
                      {evidence ? ` · ${evidence.title}` : ""}
                    </p>
                  </div>
                  {items.map((item, idx) => {
                    const edited =
                      evidence?.user_edited_fields.includes(item.field_name) ?? false;
                    return (
                      <div
                        key={item.id}
                        className={idx === 0 ? "pt-3" : "mt-4 border-t border-slate-100 pt-4"}
                      >
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-slate-600">
                            {FIELD_LABEL[item.field_name] ?? item.field_name}
                          </p>
                          {item.confidence !== null && item.confidence < 0.8 && (
                            <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">
                              置信度低，请人工确认
                            </span>
                          )}
                        </div>

                        <p className="mt-2 text-sm text-slate-600">
                          <span className="ai-badge mr-1">AI</span>
                          {valueText(item.ai_value, item.field_name)}
                        </p>

                        <label className="mt-2 block text-sm">
                          <span className="mb-1 block text-slate-500">你的版本</span>
                          <textarea
                            className="input"
                            rows={2}
                            placeholder={valueText(item.ai_value, item.field_name)}
                            value={drafts[item.id] ?? ""}
                            onChange={(e) => setDrafts({ ...drafts, [item.id]: e.target.value })}
                          />
                        </label>

                        {edited && (
                          <p className="mt-1 text-xs text-emerald-700">
                            这个字段已由你修改，后续 AI 解析不会覆盖。
                          </p>
                        )}

                        <div className="mt-2 flex gap-2">
                          <button className="btn-primary" onClick={() => void confirmItem(item)}>
                            确认
                          </button>
                          <button className="btn-ghost" onClick={() => void discardItem(item)}>
                            忽略
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </article>
              );
            })}
          </section>
        </div>
      )}
    </div>
  );
}
