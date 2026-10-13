/**
 * 单元测试：材料包编辑器的纯逻辑（9-B §7）。
 *
 * 覆盖：添加/去重、移除（只影响草稿）、上下移动、字段编辑、
 * 审核状态、保存 payload 序列化、编号与位置一致。
 * 跨案件/权限/版本冲突由后端测试覆盖（test_material_packages.py）。
 */

import { describe, expect, it } from "vitest";
import {
  addItemFromEvidence,
  displayNumberFor,
  moveItem,
  removeItem,
  toPayload,
  updateItem,
  type DraftItem,
} from "./material-package-ui";

const ev = (id: string, n: number, over: Partial<Parameters<typeof addItemFromEvidence>[1]> = {}) => ({
  id,
  title: `证据${n}`,
  evidence_number: n,
  proof_purpose: null,
  source_file_id: null,
  ...over,
});

describe("addItemFromEvidence", () => {
  it("追加条目并预填展示名称与待审核状态", () => {
    const items = addItemFromEvidence([], ev("a", 1, { proof_purpose: "证明劳动关系" }));
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      evidenceId: "a",
      displayName: "证据1",
      proofPurpose: "证明劳动关系",
      reviewStatus: "PENDING",
      itemId: null,
    });
  });

  it("重复选择同一条证据不产生重复条目", () => {
    let items = addItemFromEvidence([], ev("a", 1));
    items = addItemFromEvidence(items, ev("a", 1));
    expect(items).toHaveLength(1);
  });
});

describe("removeItem / moveItem", () => {
  const three = () =>
    ["a", "b", "c"].map((id, i) => addItemFromEvidence([], ev(id, i + 1))[0]!).filter(
      (x): x is DraftItem => Boolean(x),
    );

  it("移除只影响草稿数组", () => {
    const next = removeItem(three(), "b");
    expect(next.map((i) => i.evidenceId)).toEqual(["a", "c"]);
  });

  it("上移/下移交换相邻顺序，边界不越界", () => {
    let items = three();
    items = moveItem(items, "b", -1);
    expect(items.map((i) => i.evidenceId)).toEqual(["b", "a", "c"]);
    items = moveItem(items, "b", -1); // 已在顶部，保持不变
    expect(items.map((i) => i.evidenceId)).toEqual(["b", "a", "c"]);
    items = moveItem(items, "a", 1);
    expect(items.map((i) => i.evidenceId)).toEqual(["b", "c", "a"]);
    items = moveItem(items, "a", 1); // 已在底部
    expect(items.map((i) => i.evidenceId)).toEqual(["b", "c", "a"]);
    expect(moveItem(items, "missing", 1)).toBe(items);
  });

  it("编号始终等于 1 起始的位置序号", () => {
    const items = moveItem(three(), "c", -1);
    expect(items.map((i, idx) => displayNumberFor(idx))).toEqual([1, 2, 3]);
    expect(items[1]?.evidenceId).toBe("c");
  });
});

describe("updateItem", () => {
  it("只修改目标条目的展示名称/拟证明事项/审核状态", () => {
    const base = addItemFromEvidence([], ev("a", 1));
    const next = updateItem(base, "a", {
      displayName: "劳动合同（2022）",
      proofPurpose: "证明双方存在劳动关系",
      reviewStatus: "APPROVED",
    });
    expect(next[0]).toMatchObject({
      displayName: "劳动合同（2022）",
      proofPurpose: "证明双方存在劳动关系",
      reviewStatus: "APPROVED",
      evidenceId: "a",
    });
    // 原数组不被就地修改
    expect(base[0]?.reviewStatus).toBe("PENDING");
  });
});

describe("toPayload", () => {
  it("序列化为 9-A PUT /items 的输入形状", () => {
    const first = addItemFromEvidence([], ev("a", 1))[0]!;
    const payload = toPayload([updateItem([first], "a", { reviewStatus: "REJECTED" })[0]!]);
    expect(payload).toEqual([
      {
        evidence_id: "a",
        display_name: "证据1",
        proof_purpose: "",
        review_status: "REJECTED",
      },
    ]);
  });

  it("顺序即 payload 顺序（排序保存依赖数组顺序）", () => {
    let items: DraftItem[] = ["a", "b", "c"].map((id, i) =>
      addItemFromEvidence([], ev(id, i + 1))[0]!,
    );
    items = moveItem(items, "c", -1);
    items = moveItem(items, "c", -1);
    expect(toPayload(items).map((p) => p.evidence_id)).toEqual(["c", "a", "b"]);
  });
});
