"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import BackLink from "@/components/BackLink";
import { StageBadge, StatusBadge } from "@/components/workbench";
import { ApiError, api } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

/**
 * 导航按劳动仲裁工作流分组（docs/19）。
 * 每一项都是真实路由，没有死链接。
 */
const NAV_GROUPS: { title: string; items: { segment: string; label: string }[] }[] = [
  {
    title: "工作台",
    items: [
      { segment: "", label: "案件首页" },
      { segment: "files", label: "资料库" },
      { segment: "review", label: "AI 审核工作台" },
      { segment: "evidence", label: "证据目录" },
      { segment: "evidence-gaps", label: "材料缺口（A3）" },
      { segment: "timeline", label: "事实时间线" },
      { segment: "claims", label: "请求与证据关联" },
    ],
  },
  {
    title: "输出与开庭",
    items: [
      { segment: "material-packages", label: "材料包" },
      { segment: "export", label: "导出中心" },
      { segment: "trial-prep", label: "庭审准备" },
      { segment: "archive", label: "案件归档" },
    ],
  },
  {
    title: "其他",
    items: [{ segment: "settings", label: "设置与数据管理" }],
  },
];

/** 案件工作台外壳：顶部案件信息 + 分组侧边导航 + 内容区。 */
export default function CaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  const pathname = usePathname();
  const routeParams = useParams<{ id: string }>();
  const caseId = params?.id ?? routeParams?.id ?? "";
  const base = `/cases/${caseId}`;
  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [stage, setStage] = useState<{ stage: number; stage_label: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [detail, progress] = await Promise.all([
          api.getCase(caseId),
          api.getProgress(caseId),
        ]);
        if (cancelled) return;
        setCaseData(detail);
        setStage({ stage: progress.stage, stage_label: progress.stage_label });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return;
        // 非致命：布局继续渲染，页面自己处理错误态。
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  function isActive(segment: string) {
    if (segment === "") return pathname === base;
    return pathname === `${base}/${segment}` || pathname.startsWith(`${base}/${segment}/`);
  }

  const nav = (
    <nav className="space-y-5">
      {NAV_GROUPS.map((group) => (
        <div key={group.title}>
          <div className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            {group.title}
          </div>
          <div className="space-y-0.5">
            {group.items.map((item) => {
              const href = item.segment ? `${base}/${item.segment}` : base;
              const active = isActive(item.segment);
              return (
                <Link
                  key={item.segment}
                  href={href}
                  className={`block rounded-lg px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-slate-900 font-medium text-white"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:gap-6">
      <aside className="w-full shrink-0 lg:w-52">
        <div className="mb-3">
          <BackLink href="/cases" label="返回案件列表" />
        </div>
        {caseData ? (
          <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3">
            <div className="truncate text-sm font-medium text-slate-900" title={caseData.name}>
              {caseData.name}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={caseData.status} />
              {stage ? <StageBadge stage={stage.stage} label={stage.stage_label} /> : null}
            </div>
          </div>
        ) : null}
        <div className="hidden lg:block">{nav}</div>
        {/* 移动端：横向滚动导航 */}
        <div className="lg:hidden -mx-1 overflow-x-auto pb-1">
          <div className="flex min-w-max gap-1 px-1">
            {NAV_GROUPS.flatMap((g) => g.items).map((item) => {
              const href = item.segment ? `${base}/${item.segment}` : base;
              const active = isActive(item.segment);
              return (
                <Link
                  key={item.segment}
                  href={href}
                  className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${
                    active
                      ? "bg-slate-900 font-medium text-white"
                      : "bg-white text-slate-600 ring-1 ring-slate-200"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      </aside>
      <div className="h-[calc(100vh-120px)] min-w-0 flex-1 overflow-y-auto pr-1">{children}</div>
    </div>
  );
}
