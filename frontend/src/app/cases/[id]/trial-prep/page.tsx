"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import type { TrialPrep } from "@/lib/types";
import { PageHeader } from "@/components/workbench";

/** 与后端 services/workbench.py TRIAL_CHECKLIST 保持一致。 */
const CHECKLIST: { id: string; label: string }[] = [
  { id: "originals_safe", label: "证据原件/原始载体已妥善保存" },
  { id: "id_document", label: "本人身份证明已准备" },
  { id: "company_info", label: "企业工商登记信息已核对" },
  { id: "claim_amount", label: "仲裁请求金额与计算依据已复核" },
  { id: "timeline", label: "事实时间线已通读并核对" },
  { id: "copies_printed", label: "开庭材料份数已备齐" },
];

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; prep: TrialPrep };

/**
 * 庭审准备：庭审日期/备注 + 逐项核对清单 + 调解/裁决记录。
 * 所有内容由用户自己填写，系统不做任何预测。
 */
export default function TrialPrepPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [hearingDate, setHearingDate] = useState("");
  const [hearingNote, setHearingNote] = useState("");
  const [mediationNote, setMediationNote] = useState("");
  const [rulingNote, setRulingNote] = useState("");
  const [checklist, setChecklist] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const prep = await api.getTrialPrep(params.id);
      setState({ kind: "ready", prep });
      setHearingDate(prep.hearing_date ?? "");
      setHearingNote(prep.hearing_note ?? "");
      setMediationNote(prep.mediation_note ?? "");
      setRulingNote(prep.ruling_note ?? "");
      setChecklist(prep.checklist ?? {});
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

  async function save(body: Record<string, unknown>) {
    setSaving(true);
    setNotice(null);
    try {
      const prep = await api.updateTrialPrep(params.id, body);
      setState({ kind: "ready", prep });
      setChecklist(prep.checklist ?? {});
      setNotice("已保存。");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setSaving(false);
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

  const doneCount = CHECKLIST.filter((i) => checklist[i.id]).length;

  return (
    <div className="space-y-5">
      <PageHeader
        title="庭审准备"
        description="记录开庭信息并逐项核对准备情况。系统不会替您判断准备是否充分。"
      />

      {notice ? (
        <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600" role="status">
          {notice}
        </div>
      ) : null}

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">开庭信息</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block text-slate-500">庭审日期</span>
            <input
              type="date"
              className="input"
              value={hearingDate}
              onChange={(e) => setHearingDate(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-500">地点/庭室备注</span>
            <input
              className="input"
              placeholder="如：第一仲裁庭 / 线上开庭链接"
              value={hearingNote}
              onChange={(e) => setHearingNote(e.target.value)}
            />
          </label>
        </div>
        <button
          className="btn-primary"
          disabled={saving}
          onClick={() =>
            void save({
              hearing_date: hearingDate || null,
              hearing_note: hearingNote.trim() || null,
            })
          }
        >
          {saving ? "保存中…" : "保存开庭信息"}
        </button>
      </section>

      <section className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-600">准备清单</h2>
          <span className="text-xs text-slate-400">
            {doneCount} / {CHECKLIST.length} 已完成
          </span>
        </div>
        <ul className="divide-y divide-slate-100">
          {CHECKLIST.map((item) => (
            <li key={item.id} className="flex items-center gap-3 py-2.5">
              <input
                type="checkbox"
                id={`chk-${item.id}`}
                checked={Boolean(checklist[item.id])}
                onChange={(e) => {
                  const next = { ...checklist, [item.id]: e.target.checked };
                  setChecklist(next);
                  void save({ checklist: { [item.id]: e.target.checked } });
                }}
              />
              <label htmlFor={`chk-${item.id}`} className="cursor-pointer text-sm text-slate-700">
                {item.label}
              </label>
            </li>
          ))}
        </ul>
        <p className="text-xs text-slate-400">勾选后自动保存。</p>
      </section>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">调解与裁决记录</h2>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-500">调解意向 / 调解过程</span>
          <textarea
            className="input min-h-24"
            placeholder="如对方提出调解方案，请如实记录，便于庭前评估。"
            value={mediationNote}
            onChange={(e) => setMediationNote(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-500">裁决/调解书要点</span>
          <textarea
            className="input min-h-24"
            placeholder="收到文书后记录关键条款与履行期限。"
            value={rulingNote}
            onChange={(e) => setRulingNote(e.target.value)}
          />
        </label>
        <button
          className="btn-primary"
          disabled={saving}
          onClick={() =>
            void save({
              mediation_note: mediationNote.trim() || null,
              ruling_note: rulingNote.trim() || null,
            })
          }
        >
          {saving ? "保存中…" : "保存记录"}
        </button>
      </section>
    </div>
  );
}
