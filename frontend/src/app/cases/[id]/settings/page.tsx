"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, setToken } from "@/lib/api";
import type { CaseDetail, User } from "@/lib/types";
import { PageHeader, StatCard } from "@/components/workbench";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; user: User; caseData: CaseDetail };

/**
 * 设置与数据管理：账户信息 + 本案件真实数据概况 + 能力边界说明。
 * 没有实现的功能（云备份、加密、团队协作等）如实列出，不伪装入口。
 */
export default function CaseSettingsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [renaming, setRenaming] = useState(false);
  const [caseName, setCaseName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [user, caseData] = await Promise.all([
        api.me(),
        api.getCase(params.id),
      ]);
      setState({ kind: "ready", user, caseData });
      setCaseName(caseData.name);
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

  async function rename() {
    if (!caseName.trim()) return;
    try {
      const updated = await api.updateCase(params.id, { name: caseName.trim() });
      setState((s) => (s.kind === "ready" ? { ...s, caseData: updated } : s));
      setRenaming(false);
      setNotice("案件名称已更新。");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "重命名失败");
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

  const { user, caseData } = state;

  return (
    <div className="space-y-5">
      <PageHeader
        title="设置与数据管理"
        description="当前账号与本案件的数据概况。系统如实列出已实现与未实现的能力。"
      />

      {notice ? (
        <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600" role="status">
          {notice}
        </div>
      ) : null}

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">账户</h2>
        <div className="text-sm text-slate-700">
          <div>
            邮箱：<span className="font-medium">{user.email}</span>
          </div>
          <div className="mt-1">
            注册时间：{new Date(user.created_at).toLocaleString("zh-CN")}
          </div>
        </div>
        <button
          className="btn-ghost"
          onClick={() => {
            setToken(null);
            router.replace("/login");
          }}
        >
          退出登录
        </button>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">本案件数据概况</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="材料文件" value={caseData.file_count} />
          <StatCard label="证据条目" value={caseData.evidence_count} />
          <StatCard label="时间轴事件" value={caseData.event_count} />
          <StatCard label="仲裁请求" value={caseData.claim_count} />
        </div>
        <div className="card space-y-2">
          {renaming ? (
            <div className="flex items-center gap-2">
              <input
                className="input"
                value={caseName}
                onChange={(e) => setCaseName(e.target.value)}
              />
              <button className="btn-primary" onClick={() => void rename()}>
                保存
              </button>
              <button className="btn-ghost" onClick={() => setRenaming(false)}>
                取消
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-700">案件名称：{caseData.name}</span>
              <button className="btn-ghost" onClick={() => setRenaming(true)}>
                重命名
              </button>
            </div>
          )}
        </div>
      </section>

      <section className="card space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">能力与边界（如实说明）</h2>
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
          <li>原始文件保存在本机存储目录；数据库记录元数据与分析结果。</li>
          <li>导出功能生成 Word/PDF/ZIP；ZIP 可作离线备份，请自行保存副本。</li>
          <li>系统提供材料缺口提示与进度统计，不提供胜诉率预测或法律意见。</li>
          <li>目前未实现：云端异地备份、端到端加密、多人协作、在线立案对接。</li>
          <li>账号数据按用户隔离；删除案件为软删除，审计日志保留操作痕迹。</li>
        </ul>
      </section>
    </div>
  );
}
