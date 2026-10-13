/**
 * Pure helpers for the material-package editor (Phase 9-B).
 *
 * Kept out of the page component so the add/remove/reorder/save-payload rules
 * are unit-testable with vitest (no DOM, no network).
 */

import type {
  MaterialPackageItemInput,
  MaterialPackageItemReview,
  MaterialPackageStatus,
} from "./types";

/** Local working copy of one package item while the draft is being edited. */
export type DraftItem = {
  /** Server row id; null until the draft has been saved at least once. */
  itemId: string | null;
  evidenceId: string;
  evidenceNumber: number | null;
  sourceFileId: string | null;
  /** Evidence title at the time the row entered the draft. */
  evidenceTitle: string;
  displayName: string;
  proofPurpose: string;
  reviewStatus: MaterialPackageItemReview;
};

export const REVIEW_LABELS: Record<MaterialPackageItemReview, string> = {
  PENDING: "待审核",
  APPROVED: "已审核",
  REJECTED: "已驳回",
};

export const PACKAGE_STATUS_LABELS: Record<MaterialPackageStatus, string> = {
  DRAFT: "草稿",
  PUBLISHED: "已发布",
  ARCHIVED: "已归档",
};

export const SOURCE_STATUS_LABELS: Record<string, string> = {
  OK: "正常",
  CHANGED: "来源证据已变更",
  MISSING: "来源证据已删除或不可用",
};

/**
 * Append an evidence row to the draft. Returns the same array when the
 * evidence is already present (double click must not duplicate rows).
 */
export function addItemFromEvidence(
  items: DraftItem[],
  evidence: {
    id: string;
    title: string;
    evidence_number: number;
    proof_purpose: string | null;
    source_file_id: string | null;
  },
): DraftItem[] {
  if (items.some((i) => i.evidenceId === evidence.id)) return items;
  return [
    ...items,
    {
      itemId: null,
      evidenceId: evidence.id,
      evidenceNumber: evidence.evidence_number,
      sourceFileId: evidence.source_file_id,
      evidenceTitle: evidence.title,
      displayName: evidence.title,
      // Prefill from the evidence row: it is traceable to this evidence and
      // stays PENDING until a human approves it.
      proofPurpose: evidence.proof_purpose ?? "",
      reviewStatus: "PENDING",
    },
  ];
}

/** Remove from the working copy only — the original evidence is untouched. */
export function removeItem(items: DraftItem[], evidenceId: string): DraftItem[] {
  return items.filter((i) => i.evidenceId !== evidenceId);
}

/** Move one item one slot up (-1) or down (+1); no-op at the edges. */
export function moveItem(
  items: DraftItem[],
  evidenceId: string,
  direction: -1 | 1,
): DraftItem[] {
  const index = items.findIndex((i) => i.evidenceId === evidenceId);
  if (index < 0) return items;
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  const a = next[index];
  const b = next[target];
  if (a && b) {
    next[index] = b;
    next[target] = a;
  }
  return next;
}

export function updateItem(
  items: DraftItem[],
  evidenceId: string,
  patch: Partial<Pick<DraftItem, "displayName" | "proofPurpose" | "reviewStatus">>,
): DraftItem[] {
  return items.map((i) => (i.evidenceId === evidenceId ? { ...i, ...patch } : i));
}

/** Serialise the working copy into the Phase 9-A PUT /items payload shape. */
export function toPayload(items: DraftItem[]): MaterialPackageItemInput[] {
  return items.map((i) => ({
    evidence_id: i.evidenceId,
    display_name: i.displayName,
    proof_purpose: i.proofPurpose,
    review_status: i.reviewStatus,
  }));
}

/** Display number is always the 1-based position; never trusted from state. */
export function displayNumberFor(index: number): number {
  return index + 1;
}
