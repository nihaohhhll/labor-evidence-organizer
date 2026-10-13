/**
 * Pure helpers for the evidence-gap page (Phase 8-A3).
 *
 * Kept out of the page component so label mapping and check-basis rendering
 * are unit-testable with vitest (no DOM, no network).
 */

import type { EvidenceGapResult, GapSource, MissingItem } from "./types";

/** docs/03 §4 — the closed EvidenceType vocabulary, in Chinese. */
export const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  labor_contract: "劳动合同",
  company_notice: "公司通知",
  chat_record: "聊天记录",
  bank_statement: "银行流水",
  salary_statement: "工资单",
  attendance_record: "考勤记录",
  social_insurance: "社保",
  identity_document: "身份证明",
  company_registration: "工商信息",
  work_record: "工作记录",
  other: "其他",
};

export const SOURCE_KIND_LABELS: Record<string, string> = {
  evidence: "证据",
  event: "事件",
};

export const PRIORITY_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export function evidenceTypeLabel(type: string): string {
  return EVIDENCE_TYPE_LABELS[type] ?? type;
}

export function priorityLabel(priority: string): string {
  return PRIORITY_LABELS[priority] ?? priority;
}

export function suggestedTypeLabels(types: string[]): string {
  return types.map(evidenceTypeLabel).join("、");
}

export function describeSource(source: GapSource): string {
  const kind = SOURCE_KIND_LABELS[source.kind] ?? source.kind;
  return source.excerpt ? `${kind}：${source.excerpt}` : kind;
}

/**
 * Human-readable summary of a gap's `check_basis` (the audit trail: what
 * was searched and under which label). Unknown keys are ignored rather
 * than stringified, so new backend fields never leak raw JSON to users.
 */
export function describeCheckBasis(basis: Record<string, unknown> | null): string {
  if (!basis) return "";
  const parts: string[] = [];
  if (typeof basis.fact_label === "string") {
    parts.push(`材料中已出现的事实：${basis.fact_label}`);
  }
  if (typeof basis.fact_value === "string" && basis.fact_value) {
    parts.push(`材料中的值：${basis.fact_value}`);
  }
  if (Array.isArray(basis.expected_types)) {
    const labels = (basis.expected_types as string[]).map(evidenceTypeLabel).join("、");
    parts.push(`期望的证据类型：${labels}`);
  }
  if (typeof basis.checked_evidence_count === "number") {
    parts.push(`已检查证据 ${basis.checked_evidence_count} 份`);
  }
  if (typeof basis.checked_event_count === "number") {
    parts.push(`已检查事件 ${basis.checked_event_count} 个`);
  }
  if (typeof basis.event_id === "string") {
    parts.push(`相关事件：${basis.event_id.slice(0, 8)}…`);
  }
  if (typeof basis.precision === "string") {
    parts.push(`事件时间精度：${basis.precision}`);
  }
  return parts.join("；");
}

/** Short, readable list of related fact ids (uuid5 values, no fact table). */
export function shortFactIds(item: MissingItem): string[] {
  return item.related_fact_ids.map((id) => `${id.slice(0, 8)}…`);
}

/** Newest first, as the history endpoint already returns. */
export function orderedByVersion(results: EvidenceGapResult[]): EvidenceGapResult[] {
  return [...results].sort((a, b) => b.version - a.version);
}

export function missingCount(result: EvidenceGapResult | null): number {
  return result?.gap_json?.missing_items?.length ?? 0;
}
