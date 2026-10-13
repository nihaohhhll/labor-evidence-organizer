/**
 * 单元测试：材料缺口页的纯逻辑（Phase 8-A3）。
 *
 * 覆盖：类型/来源/优先级中文映射、未知值直通、检查依据文案、
 * 关联事实短 ID、历史版本排序、缺口计数。
 * 规则触发与闸门由后端 tests/test_evidence_gaps.py 覆盖。
 */

import { describe, expect, it } from "vitest";
import {
  describeCheckBasis,
  describeSource,
  evidenceTypeLabel,
  missingCount,
  orderedByVersion,
  priorityLabel,
  shortFactIds,
  suggestedTypeLabels,
} from "./evidence-gap-ui";
import type { EvidenceGapResult, MissingItem } from "./types";

const item = (over: Partial<MissingItem> = {}): MissingItem => ({
  code: "FACT_NO_EXPECTED_TYPE_SOURCE",
  title: "缺少入职时间相关证据",
  description: "案件材料中已提及入职时间，但未发现预期类型的证据支持。",
  related_fact_ids: ["550e8400-e29b-41d4-a716-446655440000"],
  suggested_evidence_types: ["labor_contract", "salary_statement"],
  priority: "medium",
  gap_id: "g1",
  sources: [],
  check_basis: null,
  ...over,
});

const result = (version: number, items: MissingItem[] = []): EvidenceGapResult => ({
  id: `id-${version}`,
  case_id: "case-1",
  version,
  status: "SUCCESS",
  gap_json: { missing_items: items },
  error_type: null,
  error_message: null,
  created_at: "2026-10-12T00:00:00Z",
});

describe("标签映射", () => {
  it("已知证据类型/优先级/来源映射为中文", () => {
    expect(evidenceTypeLabel("labor_contract")).toBe("劳动合同");
    expect(evidenceTypeLabel("salary_statement")).toBe("工资单");
    expect(priorityLabel("medium")).toBe("中");
    expect(describeSource({ kind: "evidence", id: "x", excerpt: "摘录" })).toBe(
      "证据：摘录",
    );
    expect(describeSource({ kind: "event", id: "x", excerpt: null })).toBe("事件");
  });

  it("未知值直通显示，不静默吞掉", () => {
    expect(evidenceTypeLabel("brand_new_type")).toBe("brand_new_type");
    expect(priorityLabel("urgent")).toBe("urgent");
    expect(describeSource({ kind: "future_kind", id: "x", excerpt: null })).toBe(
      "future_kind",
    );
  });

  it("建议类型整体转中文", () => {
    expect(suggestedTypeLabels(["labor_contract", "chat_record"])).toBe("劳动合同、聊天记录");
    expect(suggestedTypeLabels([])).toBe("");
  });
});

describe("describeCheckBasis", () => {
  it("事实类依据输出人话", () => {
    const text = describeCheckBasis({
      fact_label: "入职时间",
      fact_value: "2022-10-01",
      expected_types: ["labor_contract", "work_record"],
      checked_evidence_count: 3,
    });
    expect(text).toContain("材料中已出现的事实：入职时间");
    expect(text).toContain("材料中的值：2022-10-01");
    expect(text).toContain("期望的证据类型：劳动合同、工作记录");
    expect(text).toContain("已检查证据 3 份");
  });

  it("事件类依据输出人话", () => {
    const text = describeCheckBasis({
      event_id: "550e8400-e29b-41d4-a716-446655440000",
      precision: "unknown",
      checked_event_count: 2,
    });
    expect(text).toContain("相关事件：550e8400…");
    expect(text).toContain("事件时间精度：unknown");
    expect(text).toContain("已检查事件 2 个");
  });

  it("null 与未知键不泄漏原始 JSON", () => {
    expect(describeCheckBasis(null)).toBe("");
    expect(describeCheckBasis({ future_field: { nested: true } })).toBe("");
  });
});

describe("辅助函数", () => {
  it("关联事实短 ID 取前 8 位", () => {
    expect(shortFactIds(item())).toEqual(["550e8400…"]);
    expect(shortFactIds(item({ related_fact_ids: [] }))).toEqual([]);
  });

  it("历史版本按版本号倒序", () => {
    const ordered = orderedByVersion([result(1), result(3), result(2)]);
    expect(ordered.map((r) => r.version)).toEqual([3, 2, 1]);
  });

  it("缺口计数兼容无结果与空结果", () => {
    expect(missingCount(null)).toBe(0);
    expect(missingCount(result(1))).toBe(0);
    expect(missingCount(result(1, [item()]))).toBe(1);
  });
});
