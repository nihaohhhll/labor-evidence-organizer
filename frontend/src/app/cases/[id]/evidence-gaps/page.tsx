"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import {
  describeCheckBasis,
  describeSource,
  missingCount,
  orderedByVersion,
  priorityLabel,
  shortFactIds,
  suggestedTypeLabels,
} from "@/lib/evidence-gap-ui";
import type { EvidenceGapResult } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

export default function EvidenceGapsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [latest, setLatest] = useState<EvidenceGapResult | null>(null);
  const [history, setHistory] = useState<EvidenceGapResult[]>([]);
  const [selectedId, setSelectedId] = useState<string>("latest");
  const [analyzing, setAnalyzing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.getEvidenceGapsHistory(params.id, 20, 0);
      setHistory(orderedByVersion(h.results));
    } catch {
      // History is best-effort: the latest-result view already reports
      // auth/loading errors; an empty history simply shows no entries.
    }
  }, [params.id]);

  const loadLatest = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await api.getLatestEvidenceGaps(params.id);
      setLatest(res);
      setState({ kind: "ready" });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLatest(null);
        setState({ kind: "ready" });
        return;
      }
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "加载失败",
      });
    }
  }, [params.id, router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void loadLatest();
    void loadHistory();
  }, [loadLatest, loadHistory, router]);

  async function analyze() {
    setAnalyzing(true);
    setNotice(null);
    try {
      const res = await api.triggerEvidenceGaps(params.id);
      setLatest(res);
      setSelectedId("latest");
      setNotice(`分析完成（版本 ${res.version}，${missingCount(res)} 项缺口）`);
      await loadHistory();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "分析失败";
      setNotice(msg);
    } finally {
      setAnalyzing(false);
    }
  }

  if (state.kind === "loading") return <div className="empty-state">加载中…</div>;
  if (state.kind === "error") {
    return (
      <div className="empty-state" role="alert">
        <p>{state.message}</p>
        <button className="btn-ghost mt-3" onClick={() => void loadLatest()}>
          重试
        </button>
      </div>
    );
  }

  // Resolve which result to display from the dropdown selection.
  const displayed =
    selectedId === "latest"
      ? latest
      : history.find((r) => r.id === selectedId) ?? latest;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">材料缺口分析（A3）</h1>
          <p className="text-sm text-slate-500">
            基于现有材料检测可能缺少的证据类型，仅描述搜索结果，不暗示义务。
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={() => void analyze()}
          disabled={analyzing}
        >
          {analyzing ? "分析中…" : "开始分析"}
        </button>
      </div>

      {notice && (
        <p
          className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700"
          role="status"
        >
          {notice}
        </p>
      )}

      {!displayed ? (
        <div className="empty-state">
          暂无缺口分析结果。点击「开始分析」生成最新版本。
        </div>
      ) : (
        <div className="space-y-3">
          {/* Header card: version info + history dropdown */}
          <div className="card">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <p className="text-lg font-semibold">v{displayed.version}</p>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {displayed.status}
                </span>
                <span className="text-xs text-slate-400">
                  {missingCount(displayed)} 项缺口
                </span>
                <span className="text-xs text-slate-400">
                  {new Date(displayed.created_at).toLocaleString("zh-CN")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-slate-500" htmlFor="gap-version-select">
                  历史版本
                </label>
                <select
                  id="gap-version-select"
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
                  value={selectedId}
                  onChange={(e) => {
                    setSelectedId(e.target.value);
                    setNotice(null);
                  }}
                >
                  <option value="latest">
                    最新版本{latest ? ` (v${latest.version})` : ""}
                  </option>
                  {history.map((row) => (
                    <option key={row.id} value={row.id}>
                      v{row.version} · {missingCount(row)} 项缺口 ·{" "}
                      {new Date(row.created_at).toLocaleString("zh-CN")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Results */}
          <div>
            {(displayed.gap_json?.missing_items?.length ?? 0) === 0 ? (
              <div className="empty-state">未发现材料缺口。</div>
            ) : (
              <div className="space-y-3">
                {displayed.gap_json?.missing_items.map((item, idx) => {
                  const basis = describeCheckBasis(item.check_basis);
                  const facts = shortFactIds(item);
                  return (
                    <div key={item.gap_id || idx} className="card space-y-2">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="font-medium">{item.title}</h3>
                          <p className="mt-1 text-sm text-slate-600">
                            {item.description}
                          </p>
                        </div>
                        <span className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                          {priorityLabel(item.priority)}
                        </span>
                      </div>

                      {item.suggested_evidence_types.length > 0 && (
                        <div className="text-xs text-slate-500">
                          建议证据类型：
                          {suggestedTypeLabels(item.suggested_evidence_types)}
                        </div>
                      )}

                      {item.sources.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-xs font-medium text-slate-500">
                            来源
                          </p>
                          {item.sources.map((src, sidx) => (
                            <p
                              key={`${src.kind}-${src.id}-${sidx}`}
                              className="rounded bg-slate-50 px-2 py-1 text-xs text-slate-600"
                            >
                              {describeSource(src)}
                            </p>
                          ))}
                        </div>
                      )}

                      {facts.length > 0 && (
                        <div className="text-xs text-slate-500">
                          关联事实：{facts.join("、")}
                        </div>
                      )}

                      {basis && (
                        <p className="text-xs text-slate-400">
                          搜索依据：{basis}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
