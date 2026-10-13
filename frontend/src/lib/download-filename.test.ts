/**
 * 单元测试：Blob 下载的文件名解析（9-C 收尾验收 §三）。
 *
 * 后端 Content-Disposition 同时携带 ASCII 回退与 RFC 5987 `filename*`；
 * 前端必须优先解码 `filename*`（中文名原样到达），解析失败或缺头时
 * 回退到 plain 参数 / 调用方提供的默认名。
 */

import { describe, expect, it } from "vitest";
import { parseDownloadFilename } from "./api";

describe("parseDownloadFilename", () => {
  it("优先解码 RFC 5987 filename*（中文名）", () => {
    const header =
      "attachment; filename=\"download.pdf\"; filename*=UTF-8''%E6%9D%90%E6%96%99%E5%8C%85-%E4%BB%B2%E8%A3%81%E6%9D%90%E6%96%99%E5%8C%85.pdf";
    expect(parseDownloadFilename(header)).toBe("材料包-仲裁材料包.pdf");
  });

  it("无 filename* 时使用 plain ASCII 回退", () => {
    expect(parseDownloadFilename('attachment; filename="March Bundle v2.pdf"')).toBe(
      "March Bundle v2.pdf",
    );
    // 未加引号的裸参数
    expect(parseDownloadFilename("attachment; filename=evidence.csv")).toBe("evidence.csv");
  });

  it("缺头或两者皆不可用时返回 null（由调用方给默认名）", () => {
    expect(parseDownloadFilename(null)).toBeNull();
    expect(parseDownloadFilename("attachment")).toBeNull();
    // filename* 百分号编码损坏 → 落到 plain
    expect(
      parseDownloadFilename('attachment; filename="fallback.pdf"; filename*=UTF-8\'\'%E0%A4%A'),
    ).toBe("fallback.pdf");
  });

  it("trim 空白，空值不顶替调用方默认名", () => {
    expect(parseDownloadFilename('attachment; filename="  spaced.pdf  "')).toBe("spaced.pdf");
    expect(parseDownloadFilename("attachment; filename*=UTF-8''%20%20")).toBeNull();
  });

  it("英文名、空格与百分号编码的分号均可往返", () => {
    expect(parseDownloadFilename("attachment; filename*=UTF-8''March%20Bundle%20v2.pdf")).toBe(
      "March Bundle v2.pdf",
    );
    expect(parseDownloadFilename("attachment; filename*=UTF-8''Q1%3Bfinal.pdf")).toBe(
      "Q1;final.pdf",
    );
  });
});
