/**
 * Pure helpers for the timeline page (merge confirmation copy).
 *
 * Kept out of the page component so the confirmation text rules are
 * unit-testable with vitest (no DOM, no network).
 */

export type MergeCandidate = {
  title: string;
  event_date: string | null;
};

/**
 * Build the window.confirm message shown before merging events.
 *
 * Must name every affected event, state what the merge does, and state that
 * it cannot be undone (there is no un-merge API; `merged_into_id` is a
 * permanent redirect).
 */
export function buildMergeConfirmMessage(events: MergeCandidate[]): string {
  const list = events
    .map((ev) => `·「${ev.title}」（${ev.event_date ?? "日期未知"}）`)
    .join("\n");
  return [
    `确定合并这 ${events.length} 个事件吗？`,
    list,
    "将保留日期最早的一个事件，其余事件会被标记为已合并，不再单独显示；证据关联会转移到保留的事件上。",
    "此操作不可撤销，合并后无法拆分还原。",
  ].join("\n");
}
