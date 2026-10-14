import { describe, expect, it } from "vitest";
import { buildMergeConfirmMessage } from "./timeline-ui";

describe("buildMergeConfirmMessage", () => {
  it("names every affected event and states irreversibility", () => {
    const msg = buildMergeConfirmMessage([
      { title: "签订劳动合同", event_date: "2023-03-01" },
      { title: "口头通知辞退", event_date: null },
    ]);
    expect(msg).toContain("这 2 个事件");
    expect(msg).toContain("「签订劳动合同」（2023-03-01）");
    expect(msg).toContain("「口头通知辞退」（日期未知）");
    expect(msg).toContain("保留日期最早的一个事件");
    expect(msg).toContain("不可撤销");
  });
});
