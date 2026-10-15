"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import type { AuditEntry, CaseDetail, CaseProgress } from "@/lib/types";
import { PageHeader, StageBadge, StatusBadge, StatCard, TaskList } from "@/components/workbench";

const ACTION_LABEL: Record<string, string> = {
  "case.created": "创建案件",
  "case.updated": "更新案件",
  "case.deleted": "删除案件",
  "file.uploaded": "上传材料",
  "file.deleted": "删除材料",
  "file.downloaded": "下载材料",
  "file.retried": "重试处理",
  "analysis.run": "运行 AI 分析",
  "evidence.confirmed": "确认证据",
  "evidence.updated": "编辑证据",
  "evidence.reanalyzed": "重分析证据",
  "review.confirm": "确认审核项",
  "review.confirmed": "确认审核项",
  "review.discarded": "驳回审核项",
  "export.created": "创建导出",
  "export.downloaded": "下载导出",
  "export.deleted": "删除导出",
  "claim.created": "新增仲裁请求",
  "claim.updated": "更新仲裁请求",
  "claim.deleted": "删除仲裁请求",
  "trial_prep.updated": "更新庭审准备",
  "material_package.created": "创建材料包",
  "material_package.updated": "更新材料包",
  "material_package.items_saved": "保存材料包条目",
  "material_package.snapshot_created": "创建材料包快照",
  "material_package.deleted": "删除材料包",
};

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CaseDetail; progress: CaseProgress; activity: AuditEntry[] };

/** 案件首页：阶段、统计、待办、最近动态、叙述编辑。 */
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
      const [data, progress, audit] = await Promise.all([
        api.getCase(params.id),
        api.getProgress(params.id),
        api.listCaseAudit(params.id, 8),
      ]);
      setState({ kind: "ready", data, progress, activity: audit.items });
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
      setState((s) => (s.kind === "ready" ? { ...s, data: updated } : s));
      setNotice("案件叙述已保存。");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

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

  const { data: c, progress, activity } = state;
  const counts = progress.counts;
  const dirty = narrative !== (c.description ?? "");
  const nextHref = progress.next_action_href
    ? `/cases/${params.id}${progress.next_action_href}`
    : null;

  return (
    <div className="space-y-5">
      <PageHeader
        title={c.name}
        description="本页的阶段与任务根据真实数据推算，不包含胜诉率或法律结论预测。"
        actions={
          <>
            <StatusBadge status={c.status} />
            <StageBadge stage={progress.stage} label={progress.stage_label} />
            {nextHref ? (
              <Link href={nextHref} className="btn-primary">
                下一步
              </Link>
            ) : null}
          </>
        }
      />

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-600">工作量统计</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard
            label="材料文件"
            value={counts.files_total ?? 0}
            href={`/cases/${params.id}/files`}
          />
          <StatCard
            label="待审核建议"
            value={counts.review_pending ?? 0}
            href={`/cases/${params.id}/review`}
          />
          <StatCard
            label="证据条目"
            value={counts.evidence_total ?? 0}
            href={`/cases/${params.id}/evidence`}
          />
          <StatCard
            label="时间轴事件"
            value={counts.events_total ?? 0}
            href={`/cases/${params.id}/timeline`}
          />
          <StatCard
            label="仲裁请求"
            value={counts.claims_total ?? 0}
            href={`/cases/${params.id}/claims`}
          />
          <StatCard
            label="材料包"
            value={counts.packages_total ?? 0}
            href={`/cases/${params.id}/material-packages`}
          />
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-600">待办任务</h2>
        <TaskList caseId={params.id} tasks={progress.tasks} />
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-600">最近处理记录</h2>
        {activity.length === 0 ? (
          <div className="empty-state">还没有操作记录。</div>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
            {activity.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <span className="text-slate-700">
                  {ACTION_LABEL[entry.action] ?? entry.action}
                  {entry.metadata_json && typeof entry.metadata_json.title === "string" ? (
                    <span className="text-slate-400"> · {entry.metadata_json.title}</span>
                  ) : null}
                </span>
                <span className="text-xs text-slate-400">
                  {new Date(entry.created_at).toLocaleString("zh-CN")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 案件叙述 — 可编辑；AI 只生成草稿，保存始终由用户点击。 */}
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
