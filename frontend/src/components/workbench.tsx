"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/** 数字统计卡（案件首页）。 */
export function StatCard({
  label,
  value,
  href,
  hint,
}: {
  label: string;
  value: number;
  href?: string;
  hint?: string;
}) {
  const body = (
    <>
      <div className="text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      <div className="mt-0.5 text-sm text-slate-600">{label}</div>
      {hint ? <div className="mt-1 text-xs text-slate-400">{hint}</div> : null}
    </>
  );
  if (href) {
    return (
      <Link
        href={href}
        className="card block transition hover:border-slate-400 hover:shadow"
      >
        {body}
      </Link>
    );
  }
  return <div className="card">{body}</div>;
}

/** 阶段/状态徽章：slate 中性、violet 仅用于 AI 相关。 */
export function StageBadge({ stage, label }: { stage: number; label: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
      阶段 {stage + 1}/8 · {label}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ACTIVE: "bg-emerald-100 text-emerald-800",
    ARCHIVED: "bg-slate-200 text-slate-600",
    CLOSED: "bg-slate-200 text-slate-600",
    DRAFT: "bg-amber-100 text-amber-800",
    CONFIRMED: "bg-emerald-100 text-emerald-800",
    PENDING: "bg-amber-100 text-amber-800",
    REJECTED: "bg-rose-100 text-rose-800",
    COMPLETED: "bg-emerald-100 text-emerald-800",
    FAILED: "bg-rose-100 text-rose-800",
  };
  const label: Record<string, string> = {
    ACTIVE: "进行中",
    ARCHIVED: "已归档",
    CLOSED: "已结案",
    DRAFT: "草稿",
    CONFIRMED: "已确认",
    PENDING: "待处理",
    REJECTED: "已驳回",
    COMPLETED: "已完成",
    FAILED: "失败",
  };
  const cls = map[status] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label[status] ?? status}
    </span>
  );
}

/** 页面标题区。 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** 待办任务清单（首页/归档共用）。action_href 是案件内相对路径（如 /files）。 */
export function TaskList({
  caseId,
  tasks,
}: {
  caseId: string;
  tasks: { id: string; title: string; done: boolean; action_href: string | null; hint: string | null }[];
}) {
  if (tasks.length === 0) {
    return <div className="empty-state">暂无任务。</div>;
  }
  return (
    <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
      {tasks.map((t) => (
        <li key={t.id} className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] ${
                  t.done
                    ? "border-emerald-500 bg-emerald-500 text-white"
                    : "border-slate-300 text-transparent"
                }`}
              >
                ✓
              </span>
              <span className={`text-sm ${t.done ? "text-slate-400 line-through" : "text-slate-800"}`}>
                {t.title}
              </span>
            </div>
            {t.hint && !t.done ? (
              <div className="ml-6 mt-0.5 text-xs text-slate-400">{t.hint}</div>
            ) : null}
          </div>
          {!t.done && t.action_href ? (
            <Link
              href={`/cases/${caseId}${t.action_href}`}
              className="shrink-0 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              前往
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
