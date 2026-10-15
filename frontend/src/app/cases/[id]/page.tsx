"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CaseDetail };

/** Case dashboard: counts + editable case narrative (navigation lives in the sidebar layout). */
export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [narrative, setNarrative] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await api.getCase(params.id);
      setState({ kind: "ready", data });
      setNarrative(data.description ?? "");
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

  async function saveNarrative() {
    setSaving(true);
    setNotice(null);
    try {
      const updated = await api.updateCase(params.id, { description: narrative || null });
      setState({ kind: "ready", data: updated });
      setNotice("案件叙述已保存。");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  // AI draft: fills the textarea only — persisting stays a deliberate user save.
  async function generateNarrative() {
    if (narrative.trim() && !window.confirm("AI 生成将覆盖当前叙述文本，继续？")) return;
    setGenerating(true);
    setNotice(null);
    try {
      const res = await api.generateCaseNarrative(params.id);
      setNarrative(res.narrative);
      setNotice(`AI 已生成（${res.provider}），检查后点「保存」。`);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setGenerating(false);
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

  const c = state.data;
  const stats = [
    { label: "文件", value: c.file_count },
    { label: "证据", value: c.evidence_count },
    { label: "时间轴事件", value: c.event_count },
  ];
  const dirty = narrative !== (c.description ?? "");

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{c.name}</h1>
        </div>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{c.status}</span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="card text-center">
            <div className="text-2xl font-semibold">{s.value}</div>
            <div className="text-sm text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Case narrative — editable story of what happened */}
      <section className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-600">案件叙述</h2>
          <div className="flex items-center gap-2">
            {notice && (
              <span className="text-xs text-slate-500" role="status">
                {notice}
              </span>
            )}
            <button
              className="btn-ghost"
              disabled={generating || saving}
              onClick={() => void generateNarrative()}
            >
              {generating ? "生成中…" : "AI 生成"}
            </button>
            <button
              className="btn-primary"
              disabled={saving || generating || !dirty}
              onClick={() => void saveNarrative()}
            >
              {saving ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
        <textarea
          className="input min-h-72 w-full"
          placeholder="按时间顺序写清：何时入职、从事什么岗位、工资多少、发生了什么争议（调岗/降薪/欠薪/辞退等）、何时离职或被解除、目前诉求。这段叙述会用于生成材料缺口分析的比对基准。"
          value={narrative}
          onChange={(e) => {
            setNarrative(e.target.value);
            setNotice(null);
          }}
        />
        <p className="text-xs text-slate-400">{narrative.length} / 5000 字</p>
      </section>

      <p className="text-xs text-slate-400">
        更新于 {new Date(c.updated_at).toLocaleString("zh-CN")}
      </p>
    </div>
  );
}
