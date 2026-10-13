"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import { useFilePreview } from "@/lib/file-preview";
import {
  DraftItem,
  PACKAGE_STATUS_LABELS,
  REVIEW_LABELS,
  addItemFromEvidence,
  displayNumberFor,
  moveItem,
  removeItem,
  toPayload,
  updateItem,
} from "@/lib/material-package-ui";
import type {
  CaseFile,
  EvidenceRow,
  MaterialPackageDetail,
  MaterialPackageItemReview,
  MaterialPackageSnapshot,
  MaterialPackageStatus,
} from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | {
      kind: "error";
      message: string;
    }
  | {
      kind: "ready";
      pkg: MaterialPackageDetail;
      evidence: EvidenceRow[];
      files: CaseFile[];
      snapshots: MaterialPackageSnapshot[];
    };

/**
 * 材料包编辑页（9-B §3.2）：三区域布局。
 * A. 可选证据列表（筛选 + 选择/取消）
 * B. 材料包条目（顺序、编号、展示名称、拟证明事项、审核状态、移除）
 * C. 原始证据预览（复用文件内容接口的权限校验）
 */
export default function MaterialPackageEditPage() {
  const params = useParams<{ id: string; pkgId: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [items, setItems] = useState<DraftItem[]>([]);
  const [savedItems, setSavedItems] = useState<DraftItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [statusBusy, setStatusBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [previewEvidenceId, setPreviewEvidenceId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const pkgRef = useRef<MaterialPackageDetail | null>(null);

  const dirty = useMemo(
    () => JSON.stringify(items) !== JSON.stringify(savedItems),
    [items, savedItems],
  );

  const loadSeq = useRef(0);

  const load = useCallback(async () => {
    // Dev StrictMode runs the effect twice: overlapping loads would let a
    // stale response reset items the user just edited. Only the newest
    // sequence number may apply its result.
    const seq = ++loadSeq.current;
    setState({ kind: "loading" });
    try {
      const [pkg, ev, fl, snaps] = await Promise.all([
        api.getMaterialPackage(params.pkgId),
        api.listEvidence(params.id),
        api.listFiles(params.id),
        api.listMaterialPackageSnapshots(params.pkgId),
      ]);
      if (seq !== loadSeq.current) return;
      const serverItems: DraftItem[] = pkg.items.map((i) => ({
        itemId: i.id,
        evidenceId: i.evidence_id,
        evidenceNumber: i.evidence_number,
        sourceFileId: i.source_file_id,
        evidenceTitle: "",
        displayName: i.display_name,
        proofPurpose: i.proof_purpose ?? "",
        reviewStatus: i.review_status,
      }));
      pkgRef.current = pkg;
      setState({
        kind: "ready",
        pkg,
        evidence: ev.evidence,
        files: fl.files,
        snapshots: snaps.snapshots,
      });
      setItems(serverItems);
      setSavedItems(serverItems);
      setConflict(false);
      setNotice(null);
    } catch (err) {
      if (seq !== loadSeq.current) return; // stale failure — a newer load owns the view
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ kind: "error", message: err instanceof Error ? err.message : "加载失败" });
    }
  }, [params.id, params.pkgId, router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [load, router]);

  // Unsaved-changes guard: the browser natively confirms on tab close / refresh.
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  /** In-app navigation guard: browser confirm before leaving with unsaved edits. */
  const guardLeave = useCallback(
    (e: ReactMouseEvent<HTMLAnchorElement>) => {
      if (dirty && !window.confirm("有未保存的修改，离开将丢失这些修改。确定离开吗？")) {
        e.preventDefault();
      }
    },
    [dirty],
  );

  function toggleEvidence(ev: EvidenceRow) {
    setNotice(null);
    setItems((prev) =>
      prev.some((i) => i.evidenceId === ev.id)
        ? removeItem(prev, ev.id)
        : addItemFromEvidence(prev, ev),
    );
  }

  async function onSave() {
    const pkg = pkgRef.current;
    if (!pkg) return;
    setSaving(true);
    setNotice(null);
    setConflict(false);
    try {
      const updated = await api.saveMaterialPackageItems(
        pkg.id,
        pkg.draft_version,
        toPayload(items),
      );
      const serverItems: DraftItem[] = updated.items.map((i) => ({
        itemId: i.id,
        evidenceId: i.evidence_id,
        evidenceNumber: i.evidence_number,
        sourceFileId: i.source_file_id,
        evidenceTitle: "",
        displayName: i.display_name,
        proofPurpose: i.proof_purpose ?? "",
        reviewStatus: i.review_status,
      }));
      pkgRef.current = updated;
      setState((s) => (s.kind === "ready" ? { ...s, pkg: updated } : s));
      setItems(serverItems);
      setSavedItems(serverItems);
      setNotice("草稿已保存。");
    } catch (err) {
      if (err instanceof ApiError && err.code === "VERSION_CONFLICT") {
        setConflict(true);
      } else if (err instanceof ApiError && err.code === "NOT_EDITABLE") {
        // Archived elsewhere while editing: refresh status, keep the page usable.
        setNotice(`${err.message}（已重新加载当前状态）`);
        try {
          const updated = await api.getMaterialPackage(pkg.id);
          pkgRef.current = updated;
          setState((s) => (s.kind === "ready" ? { ...s, pkg: updated } : s));
        } catch {
          /* keep the message above */
        }
      } else {
        setNotice(err instanceof ApiError ? err.message : "保存失败，请重试");
      }
    } finally {
      setSaving(false);
    }
  }

  async function onCreateSnapshot() {
    const pkg = pkgRef.current;
    if (!pkg) return;
    setSnapshotting(true);
    setNotice(null);
    try {
      const snap = await api.createMaterialPackageSnapshot(pkg.id, pkg.draft_version);
      setNotice(`快照 v${snap.version} 已创建。`);
      await refreshPkgAndSnapshots(pkg.id);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "创建快照失败");
    } finally {
      setSnapshotting(false);
    }
  }

  async function refreshPkgAndSnapshots(pkgId: string) {
    const [updated, snaps] = await Promise.all([
      api.getMaterialPackage(pkgId),
      api.listMaterialPackageSnapshots(pkgId),
    ]);
    pkgRef.current = updated;
    setState((s) => (s.kind === "ready" ? { ...s, pkg: updated, snapshots: snaps.snapshots } : s));
  }

  /** 发布 = 纯状态标记（9-C 决策 2）：发布后仍可继续编辑。 */
  async function changeStatus(status: MaterialPackageStatus, confirmText: string) {
    const pkg = pkgRef.current;
    if (!pkg) return;
    if (!window.confirm(confirmText)) return;
    setStatusBusy(status);
    setNotice(null);
    try {
      await api.updateMaterialPackage(pkg.id, { status });
      setNotice(
        status === "PUBLISHED"
          ? "已发布。发布只是状态标记，仍可继续编辑条目。"
          : status === "ARCHIVED"
            ? "已归档，材料包转为只读。"
            : "已撤回到草稿。",
      );
      await refreshPkgAndSnapshots(pkg.id);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "状态更新失败");
    } finally {
      setStatusBusy(null);
    }
  }

  // Hooks must run unconditionally: resolve the preview source from local
  // draft state (which exists before the payload is ready).
  const previewSourceFileId = previewEvidenceId
    ? items.find((i) => i.evidenceId === previewEvidenceId)?.sourceFileId ?? null
    : null;
  const preview = useFilePreview(previewSourceFileId);

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

  const { pkg, evidence, files, snapshots } = state;
  const fileById = new Map(files.map((f) => [f.id, f]));
  const evidenceById = new Map(evidence.map((e) => [e.id, e]));
  const inDraft = new Set(items.map((i) => i.evidenceId));

  const categories = Array.from(new Set(evidence.map((e) => e.category))).sort();
  const filteredEvidence = evidence.filter((e) => {
    if (categoryFilter && e.category !== categoryFilter) return false;
    if (search && !e.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const previewItem = previewEvidenceId ? items.find((i) => i.evidenceId === previewEvidenceId) : null;
  const previewEvidence = previewItem ? evidenceById.get(previewItem.evidenceId) : null;
  const previewFile = previewSourceFileId ? fileById.get(previewSourceFileId) : null;

  // 9-C 决策 2：发布≠只读；只有 ARCHIVED（NOT_EDITABLE）才锁定编辑。
  const readonly = pkg.status === "ARCHIVED";
  const latestSnapshot = snapshots[0] ?? null;
  const snapshotStale =
    latestSnapshot !== null && latestSnapshot.draft_version_captured < pkg.draft_version;
  const statusBusyNow = statusBusy !== null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{pkg.name}</h1>
          <p className="mt-0.5 text-xs text-slate-400">
            {PACKAGE_STATUS_LABELS[pkg.status] ?? pkg.status} · 草稿版本 v{pkg.draft_version} ·
            历史快照 {pkg.snapshot_count} 个
          </p>
        </div>
        <div className="flex gap-2">
          <Link className="btn-ghost" href={`/cases/${params.id}/material-packages`} onClick={guardLeave}>
            返回列表
          </Link>
          <Link
            className="btn-ghost"
            href={`/cases/${params.id}/material-packages/${pkg.id}/history`}
            onClick={guardLeave}
          >
            历史版本
          </Link>
          <Link
            className="btn-ghost"
            href={`/cases/${params.id}/material-packages/${pkg.id}/export`}
            onClick={guardLeave}
          >
            导出成卷
          </Link>
          {!readonly && (
            <>
              <button className="btn-primary" onClick={() => void onSave()} disabled={saving || !dirty}>
                {saving ? "保存中…" : dirty ? "保存草稿 *" : "保存草稿"}
              </button>
              <button
                className="btn-ghost"
                onClick={() => void onCreateSnapshot()}
                disabled={snapshotting || dirty || items.length === 0}
                title={dirty ? "先保存草稿再创建快照" : items.length === 0 ? "材料包为空" : ""}
              >
                {snapshotting ? "创建中…" : "创建快照"}
              </button>
              {pkg.status === "DRAFT" && (
                <button
                  className="btn-ghost"
                  disabled={statusBusyNow}
                  onClick={() =>
                    void changeStatus(
                      "PUBLISHED",
                      "发布该材料包？发布只是状态标记，发布后仍可继续编辑条目。",
                    )
                  }
                >
                  {statusBusy === "PUBLISHED" ? "发布中…" : "发布"}
                </button>
              )}
              <button
                className="btn-ghost"
                disabled={statusBusyNow || dirty}
                title={dirty ? "先保存草稿再归档" : ""}
                onClick={() =>
                  void changeStatus("ARCHIVED", "归档后材料包将变为只读，确定归档？")
                }
              >
                {statusBusy === "ARCHIVED" ? "归档中…" : "归档"}
              </button>
            </>
          )}
          {readonly && (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
              已归档，只读
            </span>
          )}
        </div>
      </div>

      {dirty && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700" role="status">
          有未保存的修改，离开页面前请先保存草稿。
        </p>
      )}
      {conflict && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          材料包已被其他人修改，为避免覆盖你的修改，本次保存未生效。请重新加载最新草稿后再编辑。
          <button className="btn-ghost ml-2" onClick={() => void load()}>
            重新加载
          </button>
        </div>
      )}
      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}
      {snapshotStale && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700" role="status">
          草稿 v{pkg.draft_version} 比最新快照 v{latestSnapshot?.version}（基于草稿 v
          {latestSnapshot?.draft_version_captured}）更新。导出默认使用最新快照；要包含当前修改，
          请先创建新快照。
        </p>
      )}
      {snapshots.length === 0 && pkg.item_count > 0 && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700" role="status">
          尚未创建快照：导出成卷前需要先保存草稿并创建快照。
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* A. 可选证据列表 */}
        <section className="card space-y-3">
          <h2 className="font-medium">可选证据（{filteredEvidence.length}）</h2>
          <input
            className="input w-full"
            placeholder="按名称筛选…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="input w-full"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">全部分类</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {evidence.length === 0 ? (
            <p className="text-sm text-slate-400">当前案件还没有证据，请先在证据目录中生成。</p>
          ) : (
            <ul className="max-h-[28rem] space-y-1 overflow-y-auto">
              {filteredEvidence.map((e) => (
                <li key={e.id}>
                  <label className="flex cursor-pointer items-start gap-2 rounded p-1 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={inDraft.has(e.id)}
                      onChange={() => toggleEvidence(e)}
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-sm">
                        证据{e.evidence_number} · {e.title}
                      </span>
                      <span className="block text-xs text-slate-400">
                        {e.category} · {e.review_status}
                        {!e.source_file_id && " · 无来源文件"}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* B. 材料包条目列表 */}
        <section className="card space-y-3">
          <h2 className="font-medium">材料包条目（{items.length}）</h2>
          {items.length === 0 ? (
            <p className="text-sm text-slate-400">
              还没有条目。从左侧勾选证据加入材料包；移除条目只影响草稿，不会删除原始证据。
            </p>
          ) : (
            <ul className="space-y-2">
              {items.map((item, index) => (
                <li key={item.evidenceId} className="rounded-lg border border-slate-200 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                      证据{displayNumberFor(index)}
                    </span>
                    <span className="flex gap-1">
                      <button
                        className="btn-ghost !px-2 !py-0.5 text-xs"
                        onClick={() => setItems((prev) => moveItem(prev, item.evidenceId, -1))}
                        disabled={index === 0}
                        aria-label="上移"
                      >
                        ↑ 上移
                      </button>
                      <button
                        className="btn-ghost !px-2 !py-0.5 text-xs"
                        onClick={() => setItems((prev) => moveItem(prev, item.evidenceId, 1))}
                        disabled={index === items.length - 1}
                        aria-label="下移"
                      >
                        ↓ 下移
                      </button>
                      <button
                        className="btn-ghost !px-2 !py-0.5 text-xs"
                        onClick={() => setPreviewEvidenceId(item.evidenceId)}
                      >
                        预览
                      </button>
                      <button
                        className="!px-2 !py-0.5 text-xs text-red-600 underline"
                        onClick={() => {
                          setNotice(null);
                          setItems((prev) => removeItem(prev, item.evidenceId));
                        }}
                      >
                        移除
                      </button>
                    </span>
                  </div>
                  <input
                    className="input mt-2 w-full text-sm"
                    value={item.displayName}
                    maxLength={300}
                    placeholder="展示名称"
                    onChange={(e) =>
                      setItems((prev) => updateItem(prev, item.evidenceId, { displayName: e.target.value }))
                    }
                  />
                  <textarea
                    className="input mt-2 w-full text-sm"
                    rows={2}
                    maxLength={4000}
                    placeholder="拟证明事项（留空则沿用证据原文）"
                    value={item.proofPurpose}
                    onChange={(e) =>
                      setItems((prev) => updateItem(prev, item.evidenceId, { proofPurpose: e.target.value }))
                    }
                  />
                  <select
                    className="input mt-2 w-full text-sm"
                    value={item.reviewStatus}
                    onChange={(e) =>
                      setItems((prev) =>
                        updateItem(prev, item.evidenceId, {
                          reviewStatus: e.target.value as MaterialPackageItemReview,
                        }),
                      )
                    }
                  >
                    {(Object.keys(REVIEW_LABELS) as MaterialPackageItemReview[]).map((k) => (
                      <option key={k} value={k}>
                        {REVIEW_LABELS[k]}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* C. 原始证据预览 */}
        <section className="card space-y-3">
          <h2 className="font-medium">原始证据预览</h2>
          {!previewItem ? (
            <p className="text-sm text-slate-400">在条目列表中点击「预览」查看对应原始文件。</p>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium">{previewItem.displayName}</p>
              <p className="text-xs text-slate-400">
                证据{previewItem.evidenceNumber ?? "?"}
                {previewFile ? ` · 来源文件：${previewFile.original_filename}` : ""}
              </p>
              {!previewSourceFileId ? (
                <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
                  来源证据没有关联原始文件（可能已被删除或该证据为手工录入），无法预览。
                </p>
              ) : preview.kind === "loading" ? (
                <p className="text-sm text-slate-400">原始文件加载中…</p>
              ) : preview.kind === "error" ? (
                <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-700" role="alert">
                  来源文件不可用：{preview.message}
                </p>
              ) : preview.kind === "ready" ? (
                <>
                  {previewFile?.mime_type.startsWith("image/") ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={preview.url}
                      alt={previewFile.original_filename}
                      className="max-h-96 w-full rounded border border-slate-200 object-contain"
                    />
                  ) : previewFile?.mime_type === "application/pdf" ? (
                    <iframe
                      title="原始文件预览"
                      src={preview.url}
                      className="h-96 w-full rounded border border-slate-200"
                    />
                  ) : previewFile ? (
                    <p className="text-sm text-slate-500">该文件类型不支持内嵌预览。</p>
                  ) : (
                    <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
                      文件记录已不在列表中（可能已被删除），请在新窗口确认内容。
                    </p>
                  )}
                  <a
                    className="inline-block text-sm text-slate-600 underline"
                    href={preview.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    在新窗口打开原始文件
                  </a>
                </>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
