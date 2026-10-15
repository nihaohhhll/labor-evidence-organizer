"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import BackLink from "@/components/BackLink";

const NAV_ITEMS = [
  { segment: "", label: "案件概览" },
  { segment: "files", label: "资料库" },
  { segment: "review", label: "AI 审核工作台" },
  { segment: "timeline", label: "案件时间轴" },
  { segment: "evidence", label: "证据目录" },
  { segment: "evidence-gaps", label: "材料缺口（A3）" },
  { segment: "material-packages", label: "材料包" },
  { segment: "export", label: "导出中心" },
] as const;

/** Case workspace layout: persistent left sidebar + content area. */
export default function CaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  const pathname = usePathname();
  const base = `/cases/${params.id}`;

  return (
    <div className="flex gap-6">
      <aside className="w-48 shrink-0">
        <div className="mb-4">
          <BackLink href="/cases" label="返回案件列表" />
        </div>
        <nav className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const href = item.segment ? `${base}/${item.segment}` : base;
            const active =
              item.segment === ""
                ? pathname === base
                : pathname === href || pathname.startsWith(href + "/");
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
        </nav>
      </aside>
      <div className="h-[calc(100vh-120px)] min-w-0 flex-1 overflow-y-auto pr-1">
        {children}
      </div>
    </div>
  );
}
