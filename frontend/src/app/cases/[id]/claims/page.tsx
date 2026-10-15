"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import type { Claim, EvidenceRow, TimelineEvent } from "@/lib/types";
import { PageHeader, StatusBadge } from "@/components/workbench";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; claims: Claim[]; evidence: EvidenceRow[]; events: TimelineEvent[] };

const EMPTY_FORM = {
  title: "",
  description: "",
  amount: "",
  calculation: "",
  notes: "",
};

/**
 * 请求与证据关联：仲裁请求 → 相关事实 → 证据。
 * 关联选择在编辑卡片内完成，无假数据；状态仅 DRAFT/CONFIRMED 两档。
 */
export default function ClaimsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<Claim>>({});

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [claims, evidence, events] = await Promise.all([
        api.listClaims(params.id),
        api.listEvidence(params.id),
        api.listEvents(params.id),
      ]);
      setState({
        kind: "ready",
        claims: claims.claims,
        evidence: evidence.evidence,
        events: events.events,
      });
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

  async function createClaim() {
    if (!form.title.trim()) {
      setNotice("请填写请求名称。");
      return;
    }
    setCreating(true);
    setNotice(null);
    try {
      await api.createClaim(params.id, {
        title: form.title.trim(),
        description: form.description.trim() || null,
        amount: form.amount.trim() || null,
        calculation: form.calculation.trim() || null,
        notes: form.notes.trim() || null,
      });
      setForm(EMPTY_FORM);
      setNotice("已新增仲裁请求。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "新增失败");
    } finally {
      setCreating(false);
    }
  }

  async function patchClaim(claim: Claim, body: Record<string, unknown>) {
    setBusyId(claim.id);
    setNotice(null);
    try {
      await api.updateClaim(claim.id, body);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusyId(null);
    }
  }

  async function removeClaim(claim: Claim) {
    if (!window.confirm(`删除仲裁请求「${claim.title}」？该操作不可撤销。`)) return;
    setBusyId(claim.id);
    try {
      await api.deleteClaim(claim.id);
      setNotice("已删除。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "删除失败");
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

  const { claims, evidence, events } = state;

  return (
    <div className="space-y-5">
      <PageHeader
        title="请求与证据关联"
        description="写明每一项仲裁请求、金额与计算依据，并关联支撑它的事实与证据。"
      />

      {notice ? (
        <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600" role="status">
          {notice}
        </div>
      ) : null}

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">新增仲裁请求</h2>
        <input
          className="input"
          placeholder="请求名称，如：请求支付违法解除赔偿金"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <textarea
          className="input min-h-20"
          placeholder="请求内容说明（可选）"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <input
            className="input"
            placeholder="金额（按原文填写，如 15000 元）"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
          <input
            className="input"
            placeholder="计算依据，如 7500 × 2 个月"
            value={form.calculation}
            onChange={(e) => setForm({ ...form, calculation: e.target.value })}
          />
        </div>
        <input
          className="input"
          placeholder="备注（可选）"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
        />
        <button className="btn-primary" disabled={creating} onClick={() => void createClaim()}>
          {creating ? "新增中…" : "新增请求"}
        </button>
      </section>

      {claims.length === 0 ? (
        <div className="empty-state">还没有仲裁请求，先在上方新增一项。</div>
      ) : (
        <section className="space-y-4">
          {claims.map((claim) => {
            const editing = editingId === claim.id;
            const linkedEvidence = evidence.filter((e) => claim.evidence_ids.includes(e.id));
            const linkedEvents = events.filter((ev) => claim.event_ids.includes(ev.id));
            return (
              <article key={claim.id} className="card space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-medium text-slate-900">{claim.title}</h3>
                      <StatusBadge status={claim.status} />
                    </div>
                    {claim.description ? (
                      <p className="mt-1 text-sm text-slate-600">{claim.description}</p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      className="btn-ghost"
                      disabled={busyId === claim.id}
                      onClick={() => {
                        if (editing) {
                          setEditingId(null);
                        } else {
                          setEditingId(claim.id);
                          setEditDraft({
                            title: claim.title,
                            description: claim.description,
                            amount: claim.amount,
                            calculation: claim.calculation,
                            notes: claim.notes,
                            status: claim.status,
                            evidence_ids: claim.evidence_ids,
                            event_ids: claim.event_ids,
                          });
                        }
                      }}
                    >
                      {editing ? "收起" : "编辑"}
                    </button>
                    <button
                      className="btn-ghost"
                      disabled={busyId === claim.id}
                      onClick={() => void removeClaim(claim)}
                    >
                      删除
                    </button>
                  </div>
                </div>

                <div className="grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <span className="text-slate-400">金额：</span>
                    <span className="text-slate-800">{claim.amount || "未填写"}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">计算依据：</span>
                    <span className="text-slate-800">{claim.calculation || "未填写"}</span>
                  </div>
                </div>

                <div className="space-y-1 text-sm">
                  <div className="text-slate-400">关联事实（时间轴事件）：</div>
                  {linkedEvents.length === 0 ? (
                    <div className="text-slate-500">未关联。编辑后从时间轴事件中勾选。</div>
                  ) : (
                    <ul className="list-inside list-disc text-slate-700">
                      {linkedEvents.map((ev) => (
                        <li key={ev.id}>
                          {ev.event_date ?? "日期待定"} · {ev.title}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="space-y-1 text-sm">
                  <div className="text-slate-400">关联证据：</div>
                  {linkedEvidence.length === 0 ? (
                    <div className="text-slate-500">未关联。编辑后从证据目录中勾选。</div>
                  ) : (
                    <ul className="list-inside list-disc text-slate-700">
                      {linkedEvidence.map((ev) => (
                        <li key={ev.id}>
                          证据 {ev.evidence_number} · {ev.title}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {editing ? (
                  <div className="space-y-3 border-t border-slate-100 pt-3">
                    <input
                      className="input"
                      value={String(editDraft.title ?? "")}
                      onChange={(e) => setEditDraft({ ...editDraft, title: e.target.value })}
                    />
                    <div className="grid gap-3 sm:grid-cols-2">
                      <input
                        className="input"
                        placeholder="金额"
                        value={String(editDraft.amount ?? "")}
                        onChange={(e) => setEditDraft({ ...editDraft, amount: e.target.value })}
                      />
                      <input
                        className="input"
                        placeholder="计算依据"
                        value={String(editDraft.calculation ?? "")}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, calculation: e.target.value })
                        }
                      />
                    </div>
                    <textarea
                      className="input min-h-16"
                      placeholder="说明"
                      value={String(editDraft.description ?? "")}
                      onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
                    />
                    <div>
                      <div className="mb-1 text-xs font-medium text-slate-500">关联事实</div>
                      <div className="max-h-32 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                        {events.length === 0 ? (
                          <div className="text-xs text-slate-400">
                            时间轴还没有事件，先到<Link className="underline" href={`/cases/${params.id}/timeline`}>事实时间线</Link>构建。
                          </div>
                        ) : (
                          events.map((ev) => {
                            const checked = (editDraft.event_ids ?? []).includes(ev.id);
                            return (
                              <label key={ev.id} className="flex items-center gap-2 text-sm">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(e) => {
                                    const cur = new Set(editDraft.event_ids ?? []);
                                    if (e.target.checked) cur.add(ev.id);
                                    else cur.delete(ev.id);
                                    setEditDraft({ ...editDraft, event_ids: [...cur] });
                                  }}
                                />
                                <span className="truncate">
                                  {ev.event_date ?? "日期待定"} · {ev.title}
                                </span>
                              </label>
                            );
                          })
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-xs font-medium text-slate-500">关联证据</div>
                      <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                        {evidence.length === 0 ? (
                          <div className="text-xs text-slate-400">
                            还没有证据，先到<Link className="underline" href={`/cases/${params.id}/evidence`}>证据目录</Link>确认条目。
                          </div>
                        ) : (
                          evidence.map((ev) => {
                            const checked = (editDraft.evidence_ids ?? []).includes(ev.id);
                            return (
                              <label key={ev.id} className="flex items-center gap-2 text-sm">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(e) => {
                                    const cur = new Set(editDraft.evidence_ids ?? []);
                                    if (e.target.checked) cur.add(ev.id);
                                    else cur.delete(ev.id);
                                    setEditDraft({ ...editDraft, evidence_ids: [...cur] });
                                  }}
                                />
                                <span className="truncate">
                                  证据 {ev.evidence_number} · {ev.title}（
                                  {ev.review_status === "CONFIRMED" ? "已确认" : "待确认"}）
                                </span>
                              </label>
                            );
                          })
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <select
                        className="input w-auto"
                        value={String(editDraft.status ?? claim.status)}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, status: e.target.value as Claim["status"] })
                        }
                      >
                        <option value="DRAFT">草稿</option>
                        <option value="CONFIRMED">已确认</option>
                      </select>
                      <button
                        className="btn-primary"
                        disabled={busyId === claim.id}
                        onClick={() => {
                          void patchClaim(claim, {
                            title: String(editDraft.title ?? claim.title),
                            description: (editDraft.description as string | null) ?? null,
                            amount: (editDraft.amount as string | null) || null,
                            calculation: (editDraft.calculation as string | null) || null,
                            status: editDraft.status ?? claim.status,
                            evidence_ids: editDraft.evidence_ids ?? claim.evidence_ids,
                            event_ids: editDraft.event_ids ?? claim.event_ids,
                          }).then(() => setEditingId(null));
                        }}
                      >
                        保存修改
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
