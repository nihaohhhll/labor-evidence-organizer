"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import type { EvidenceRow } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; rows: EvidenceRow[] };

const CATEGORY_LABEL: Record<string, string> = {
  labor_contract: "劳动合同",
  company_notice: "公司通知",
  chat_record: "聊天记录",
  bank_statement: "银行流水",
  salary_statement: "工资单",
  attendance_record: "考勤记录",
  social_insurance: "社保",
  identity_document: "身份证明",
  company_registration: "工商信息",
  work_record: "工作记录",
  other: "其他",
};

/** 证据目录: review and edit AI-suggested evidence. */
export default function EvidencePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<EvidenceRow>>({});
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await api.listEvidence(params.id);
      setState({ kind: "ready", rows: res.evidence });
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

  function startEdit(row: EvidenceRow) {
    setEditing(row.id);
    setDraft({ title: row.title, summary: row.summary, proof_purpose: row.proof_purpose });
  }

  async function save(row: EvidenceRow) {
    setNotice(null);
    try {
      await api.updateEvidence(row.id, {
        title: draft.title ?? row.title,
        summary: draft.summary ?? null,
        proof_purpose: draft.proof_purpose ?? null,
      });
      setEditing(null);
      setNotice("已保存你的修改，后续 AI 解析不会覆盖它。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  async function confirm(row: EvidenceRow) {
    try {
      await api.confirmEvidence(row.id);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "确认失败");
    }
  }

  async function reanalyze(row: EvidenceRow) {
    setNotice(null);
    try {
      const updated = await api.reanalyzeEvidence(row.id);
      const kept = updated.user_edited_fields.length > 0;
      setNotice(
        kept
          ? `已重新解析。你修改过的字段（${updated.user_edited_fields.join("、")}）保持不变。`
          : "已重新解析。",
      );
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "重新解析失败");
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
        <h1 className="text-xl font-semibold">证据目录</h1>
        <button className="btn-ghost" onClick={() => void load()}>
          刷新
        </button>
      </div>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}

      {state.rows.length === 0 ? (
        <div className="empty-state">
          还没有证据。先到「资料库」上传材料并点「全部解析」。
        </div>
      ) : (
        <ul className="space-y-3">
          {state.rows.map((row) => (
            <li key={row.id} className="card space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    证据{row.evidence_number} · {row.title}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {CATEGORY_LABEL[row.category] ?? row.category}
                    {row.event_date ? ` · ${row.event_date}` : " · 时间未知"}
                    {row.confidence !== null ? ` · 置信度 ${(row.confidence * 100).toFixed(0)}%` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      row.review_status === "CONFIRMED"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-orange-100 text-orange-700"
                    }`}
                  >
                    {row.review_status === "CONFIRMED" ? "已确认" : "待确认"}
                  </span>
                  {row.user_edited_fields.length > 0 && (
                    <span className="rounded bg-slate-900 px-2 py-0.5 text-xs text-white">
                      已人工修改
                    </span>
                  )}
                </div>
              </div>

              {editing === row.id ? (
                <div className="space-y-2 border-t border-slate-100 pt-3">
                  <label className="block text-sm">
                    <span className="mb-1 block text-slate-600">证据名称</span>
                    <input
                      className="input"
                      value={draft.title ?? ""}
                      onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block text-slate-600">内容摘要</span>
                    <textarea
                      className="input"
                      rows={3}
                      value={draft.summary ?? ""}
                      onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block text-slate-600">证明目的</span>
                    <textarea
                      className="input"
                      rows={2}
                      value={draft.proof_purpose ?? ""}
                      onChange={(e) => setDraft({ ...draft, proof_purpose: e.target.value })}
                    />
                  </label>
                  <div className="flex gap-2">
                    <button className="btn-primary" onClick={() => void save(row)}>
                      保存
                    </button>
                    <button className="btn-ghost" onClick={() => setEditing(null)}>
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-1 border-t border-slate-100 pt-3 text-sm">
                  {row.summary && <p className="text-slate-700">{row.summary}</p>}
                  {row.proof_purpose && (
                    <p className="text-slate-500">
                      <span className="ai-badge mr-1">AI 建议</span>
                      {row.proof_purpose}
                    </p>
                  )}
                  <div className="flex gap-3 pt-1">
                    <button className="text-sm text-slate-600 underline" onClick={() => startEdit(row)}>
                      修改
                    </button>
                    {row.review_status !== "CONFIRMED" && (
                      <button className="text-sm text-emerald-700 underline" onClick={() => void confirm(row)}>
                        确认
                      </button>
                    )}
                    <button className="text-sm text-slate-600 underline" onClick={() => void reanalyze(row)}>
                      重新解析
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
