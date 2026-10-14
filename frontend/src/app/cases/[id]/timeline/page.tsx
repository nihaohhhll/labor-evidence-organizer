"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";
import { buildMergeConfirmMessage } from "@/lib/timeline-ui";
import type { TimelineEvent } from "@/lib/types";

type ViewState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; events: TimelineEvent[] };

/** 案件时间轴: build from evidence, edit dates, merge and delete. */
export default function TimelinePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<ViewState>({ kind: "loading" });
  const [selected, setSelected] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDate, setNewDate] = useState("");

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await api.listEvents(params.id);
      setState({ kind: "ready", events: res.events });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setState({ kind: "error", message: err instanceof Error ? err.message : "加载失败" });
    }
  }, [params.id, router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [load, router]);

  async function build() {
    setBuilding(true);
    setNotice(null);
    try {
      const res = await api.buildTimeline(params.id);
      setNotice(`时间轴已生成，共 ${res.events.length} 个事件。`);
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setBuilding(false);
    }
  }

  async function addEvent() {
    if (!newTitle.trim()) return;
    setNotice(null);
    try {
      await api.createEvent(params.id, {
        title: newTitle.trim(),
        event_date: newDate || null,
        precision: newDate ? "day" : "unknown",
      });
      setNewTitle("");
      setNewDate("");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "新增失败");
    }
  }

  async function changeDate(ev: TimelineEvent, date: string) {
    try {
      await api.updateEvent(ev.id, {
        event_date: date || null,
        precision: date ? "day" : "unknown",
      });
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "修改失败");
    }
  }

  async function remove(ev: TimelineEvent) {
    if (!window.confirm(`确定删除事件「${ev.title}」吗？`)) return;
    try {
      await api.deleteEvent(ev.id);
      setSelected((s) => s.filter((x) => x !== ev.id));
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function merge() {
    if (selected.length < 2 || state.kind !== "ready") return;
    const chosen = state.events.filter((ev) => selected.includes(ev.id));
    if (chosen.length < 2) return;
    if (!window.confirm(buildMergeConfirmMessage(chosen))) return;
    setNotice(null);
    try {
      await api.mergeEvents(selected);
      setSelected([]);
      setNotice("已合并为一个事件，证据关联已保留。");
      await load();
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "合并失败");
    }
  }

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">案件时间轴</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => void merge()} disabled={selected.length < 2}>
            合并所选（{selected.length}）
          </button>
          <button className="btn-primary" onClick={() => void build()} disabled={building}>
            {building ? "生成中…" : "从证据生成"}
          </button>
        </div>
      </div>

      {notice && (
        <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" role="status">
          {notice}
        </p>
      )}

      <div className="card flex flex-wrap items-end gap-2">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">新增事件</span>
          <input
            className="input"
            placeholder="例如：HR 口头通知辞退"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">日期（可空）</span>
          <input
            className="input"
            type="date"
            value={newDate}
            onChange={(e) => setNewDate(e.target.value)}
          />
        </label>
        <button className="btn-primary" onClick={() => void addEvent()}>
          添加
        </button>
      </div>

      {state.events.length === 0 ? (
        <div className="empty-state">还没有时间轴事件。先确认证据，再点「从证据生成」。</div>
      ) : (
        <ol className="relative ml-3 space-y-4 border-l-2 border-slate-200 pl-5">
          {state.events.map((ev) => (
            <li key={ev.id} className="relative">
              <span
                className={`absolute -left-[27px] top-2 h-3 w-3 rounded-full border-2 border-white ${
                  ev.review_status === "CONFIRMED" ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
              <div className="card">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selected.includes(ev.id)}
                      onChange={() => toggle(ev.id)}
                      aria-label={`选择事件 ${ev.title}`}
                    />
                    <div>
                      <p className="font-medium">{ev.title}</p>
                      <input
                        type="date"
                        className="input mt-1 w-40"
                        value={ev.event_date ?? ""}
                        onChange={(e) => void changeDate(ev, e.target.value)}
                        aria-label="事件日期"
                      />
                      {ev.event_date === null && (
                        <p className="mt-1 text-xs text-amber-700">时间未知，请人工补充</p>
                      )}
                    </div>
                  </div>
                  <button
                    className="shrink-0 text-sm text-red-600 underline"
                    onClick={() => void remove(ev)}
                  >
                    删除
                  </button>
                </div>
                {ev.description && (
                  <p className="mt-2 text-sm text-slate-500">{ev.description}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
