import { expect, test, type Page } from "@playwright/test";
import {
  addItems,
  apiJson,
  createCase,
  createEvidence,
  createPackage,
  createSnapshot,
  newAuthorizedApi,
  registerUser,
  seedAuth,
  type TestUser,
} from "./helpers";

/**
 * Phase 9-C UI E2E — the 11 approved scenarios:
 *  1. empty list → create draft → edit opens
 *  2. add evidence → save draft → snapshot
 *  3. publish is a status mark: still editable after publishing (决策 2)
 *  4. draft newer than latest snapshot → divergence reminder
 *  5. archive → read-only UI + API 409 NOT_EDITABLE (统一错误码)
 *  6. package volume export: generate PDF + authenticated download
 *  7. gap appendix toggle: disabled without A3, enabled after analysis
 *  8. no snapshot → export page guidance (SNAPSHOT_REQUIRED 由后端保障)
 *  9. case export center download carries auth (401 bare-link fix)
 *  10. package list requests limit=100 (20-item silent truncation fix)
 *  11. draft delete requires confirm (cancel keeps, accept removes)
 *  12. download filename compatibility: Chinese / English+space / special chars
 */

// One account per run: /auth/register allows only 5/min per IP.
let sharedUserPromise: Promise<TestUser> | null = null;
function sharedUser(): Promise<TestUser> {
  if (!sharedUserPromise) sharedUserPromise = registerUser("shared");
  return sharedUserPromise;
}

async function setupUser(
  page: Page,
): Promise<{ user: TestUser; api: Awaited<ReturnType<typeof newAuthorizedApi>> }> {
  const user = await sharedUser();
  await seedAuth(page, user.token);
  const api = await newAuthorizedApi(user.token);
  return { user, api };
}

function onConfirm(page: Page, decide: () => "accept" | "dismiss"): void {
  page.on("dialog", async (d) => {
    expect(d.type()).toBe("confirm");
    if (decide() === "accept") await d.accept();
    else await d.dismiss();
  });
}

test("1. 空列表 → 新建材料包 → 编辑页打开（DRAFT 控件齐全）", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S1 案件");

  await page.goto(`/cases/${caseId}/material-packages`);
  await expect(page.getByText("还没有材料包。")).toBeVisible();

  await page.getByRole("link", { name: "新建材料包" }).first().click();
  await page.waitForURL(/\/material-packages\/new$/);
  await page.getByPlaceholder("例如：仲裁提交材料（第一版）").fill("仲裁提交材料（第一版）");
  await page.getByRole("button", { name: "创建草稿" }).click();
  await waitForEditPage(page);

  await expect(page.getByRole("heading", { name: "仲裁提交材料（第一版）" })).toBeVisible();
  await expect(page.getByText(/草稿 · 草稿版本 v1/)).toBeVisible();
  await expect(page.getByRole("button", { name: "保存草稿" })).toBeVisible();
  await expect(page.getByRole("button", { name: "创建快照" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发布" })).toBeVisible();
  await expect(page.getByRole("link", { name: "导出成卷" })).toBeVisible();
});

test("2. 勾选证据 → 保存草稿 → 创建快照", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S2 案件");
  const evId = await createEvidence(api, caseId, "工资条");
  const pkgId = await createPackage(api, caseId, "S2 材料包");

  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/edit`);
  await waitForEditPage(page);
  // Dev StrictMode mounts `load()` twice; wait until both settle so the
  // checkbox click cannot land between two state resets.
  await page.waitForLoadState("networkidle");

  const firstEvidence = page.getByRole("checkbox").first();
  // check() verifies the DOM state immediately after its click, which races
  // React's controlled re-render; click + polled assertion is deterministic.
  await firstEvidence.click();
  await expect(firstEvidence).toBeChecked();
  const save = page.getByRole("button", { name: /保存草稿 \*/ });
  await expect(save).toBeVisible();
  await save.click();
  await expect(page.getByText("草稿已保存。")).toBeVisible();
  await expect(page.getByText(/草稿版本 v2/)).toBeVisible();

  await page.getByRole("button", { name: "创建快照" }).click();
  await expect(page.getByText("快照 v1 已创建。")).toBeVisible();
  await expect(page.getByText(/历史快照 1 个/)).toBeVisible();
  void evId;
});

test("3. 发布 = 纯状态标记，发布后仍可继续编辑（决策 2）", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S3 案件");
  const evId = await createEvidence(api, caseId, "考勤记录");
  const pkgId = await createPackage(api, caseId, "S3 材料包");
  await addItems(api, pkgId, [evId]);
  await createSnapshot(api, pkgId);

  onConfirm(page, () => "accept");
  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/edit`);
  await waitForEditPage(page);

  await page.getByRole("button", { name: "发布" }).click();
  await expect(page.getByText(/已发布。发布只是状态标记/)).toBeVisible();
  await expect(page.getByText(/已发布 · 草稿版本/)).toBeVisible();

  // Editing controls must still be there and actually save.
  await expect(page.getByRole("button", { name: /保存草稿/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "创建快照" })).toBeVisible();
  await page.getByPlaceholder("展示名称").fill("发布后修改的名称");
  await page.getByRole("button", { name: /保存草稿 \*/ }).click();
  await expect(page.getByText("草稿已保存。")).toBeVisible();
});

test("4. 草稿比最新快照新时出现分歧提醒", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S4 案件");
  const evId = await createEvidence(api, caseId, "劳动合同");
  const pkgId = await createPackage(api, caseId, "S4 材料包");
  await addItems(api, pkgId, [evId]);
  await createSnapshot(api, pkgId);

  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/edit`);
  await waitForEditPage(page);
  // Saved draft is newer than the snapshot → the reminder shows.
  await page.getByPlaceholder("展示名称").fill("快照后的修改");
  await page.getByRole("button", { name: /保存草稿 \*/ }).click();
  await expect(page.getByText(/比最新快照 v1/)).toBeVisible();
  await expect(page.getByText(/导出默认使用最新快照/)).toBeVisible();
});

test("5. 归档 → 只读 UI + 后端统一 409 NOT_EDITABLE", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S5 案件");
  const evId = await createEvidence(api, caseId, "聊天记录");
  const pkgId = await createPackage(api, caseId, "S5 材料包");
  await addItems(api, pkgId, [evId]);

  onConfirm(page, () => "accept");
  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/edit`);
  await waitForEditPage(page);

  await page.getByRole("button", { name: "归档" }).click();
  await expect(page.getByText("已归档，只读")).toBeVisible();
  await expect(page.getByRole("button", { name: /保存草稿/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "创建快照" })).toHaveCount(0);

  // The same code the API returns for any archived-package edit.
  const put = await api.put(`material-packages/${pkgId}/items`, {
    data: {
      expected_draft_version: 2,
      items: [{ evidence_id: evId, display_name: "归档后改名" }],
    },
  });
  expect(put.status()).toBe(409);
  const body = await put.json();
  expect(body.error.code).toBe("NOT_EDITABLE");
});

test("6. 材料包导出页：生成 PDF 卷宗并带鉴权下载", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S6 案件");
  const evId = await createEvidence(api, caseId, "工资条", "入职时间：2022-10-01");
  const pkgId = await createPackage(api, caseId, "S6 成卷");
  await addItems(api, pkgId, [evId]);
  await createSnapshot(api, pkgId);

  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/export`);
  await expect(page.getByRole("heading", { name: "导出成卷：S6 成卷" })).toBeVisible();
  await page.getByRole("radio", { name: "PDF 卷宗（pdf）" }).check();
  await page.getByRole("button", { name: "生成卷宗" }).click();

  await expect(page.getByText(/已从快照 v1 生成 PDF 卷宗/)).toBeVisible();
  const record = page.locator("li.card", { hasText: "PDF 卷宗（pdf）" });
  await expect(record.getByText("快照 v1")).toBeVisible();
  await expect(record.getByText("已完成")).toBeVisible();

  await installDownloadSpy(page);
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    record.getByRole("button", { name: "下载" }).click(),
  ]);
  expect(await download.failure()).toBeNull();
  // Playwright 的 headless Chromium 会丢弃含非 ASCII 字符的 a.download 值
  // （裸锚点探测亦复现），因此在页面侧拦截锚点点击，断言真实赋给
  // a.download 的保存名 = filename* 解析结果（真实响应头驱动整条解析链）。
  expect(await readDownloadName(page)).toBe("材料包-S6 成卷.pdf");
  const path = await download.path();
  expect(path).toBeTruthy();
  const { readFileSync } = await import("node:fs");
  expect(readFileSync(path!).subarray(0, 5).toString("latin1")).toBe("%PDF-");
});

test("7. 完整性附录开关：无 A3 结果禁用，分析后可用", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S7 案件");
  const evId = await createEvidence(api, caseId, "聊天记录", "入职时间：2022-10-01");
  const pkgId = await createPackage(api, caseId, "S7 材料包");
  await addItems(api, pkgId, [evId]);
  await createSnapshot(api, pkgId);

  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/export`);
  const appendix = page.getByRole("checkbox", { name: /附录：材料完整性提示/ });
  await expect(appendix).toBeDisabled();
  await expect(page.getByText(/尚无可用的材料缺口分析结果/)).toBeVisible();

  const gap = await api.post(`cases/${caseId}/evidence-gaps`);
  expect(gap.status()).toBe(200);

  await page.reload();
  await expect(appendix).toBeEnabled();
  await appendix.check();
  await page.getByRole("button", { name: "生成卷宗" }).click();
  await expect(page.getByText(/已从快照 v1 生成 Word 卷宗/)).toBeVisible();
  const record = page.locator("li.card", { hasText: "Word 卷宗（docx）" }).first();
  await expect(record.getByText("含完整性附录")).toBeVisible();
});

test("8. 无快照时导出页给出创建快照引导", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S8 案件");
  const evId = await createEvidence(api, caseId, "工资条");
  const pkgId = await createPackage(api, caseId, "S8 无快照");
  await addItems(api, pkgId, [evId]);

  await page.goto(`/cases/${caseId}/material-packages/${pkgId}/export`);
  await expect(page.getByText(/尚无快照。请先在编辑页保存草稿并创建快照/)).toBeVisible();
  await expect(page.getByRole("button", { name: "生成卷宗" })).toHaveCount(0);

  // Backend guarantees the same precondition (409 SNAPSHOT_REQUIRED).
  const res = await api.post(`material-packages/${pkgId}/exports`, {
    data: { format: "pdf" },
  });
  expect(res.status()).toBe(409);
  expect((await res.json()).error.code).toBe("SNAPSHOT_REQUIRED");
});

test("9. 案件导出中心下载携带鉴权（修复 401 裸链接）", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S9 案件");
  await createEvidence(api, caseId, "劳动合同");

  await page.goto(`/cases/${caseId}/export`);
  await page.getByRole("button", { name: "Word（证据目录 + 时间轴）" }).click();
  const job = page.locator("li.card").first();
  await expect(job.getByText("已完成")).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    job.getByRole("button", { name: "下载" }).click(),
  ]);
  expect(await download.failure()).toBeNull();
  const path = await download.path();
  expect(path).toBeTruthy();
  const { readFileSync } = await import("node:fs");
  // A 401 response would be JSON, not the docx zip container.
  expect(readFileSync(path!).subarray(0, 2).toString("latin1")).toBe("PK");
});

test("10. 材料包列表按 limit=100 拉取（修复 20 条静默截断）+ 超限提示", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S10 案件");
  for (let i = 1; i <= 101; i++) {
    await createPackage(api, caseId, `pkg-${i}`);
  }

  await page.goto(`/cases/${caseId}/material-packages`);
  await expect(page.getByText("共 101 个材料包，当前一次最多显示 100 个")).toBeVisible();
  await expect(page.getByText("pkg-101")).toBeVisible();
  // One "历史版本" link per rendered row — the old default (limit=20) showed 20.
  await expect(page.locator("a", { hasText: "历史版本" })).toHaveCount(100);
});

test("11. 草稿删除必须 confirm：取消保留、确认删除", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S11 案件");
  const pkgId = await createPackage(api, caseId, "待删除草稿");

  let decide: "accept" | "dismiss" = "dismiss";
  onConfirm(page, () => decide);

  await page.goto(`/cases/${caseId}/material-packages`);
  await page.getByRole("button", { name: "删除" }).click();
  await page.waitForTimeout(300); // let the dismissed dialog settle
  await expect(page.getByText("待删除草稿")).toBeVisible();

  decide = "accept";
  await page.getByRole("button", { name: "删除" }).click();
  await expect(page.getByText("「待删除草稿」已删除。")).toBeVisible();
  // The row (not the notice, which quotes the name) must be gone.
  await expect(page.locator("li", { hasText: "待删除草稿" })).toHaveCount(0);

  const detail = await apiJson(api, "get", `/material-packages/${pkgId}`);
  expect(detail.status).toBe(404);
});

test("12. 下载文件名兼容：英文/空格/特殊字符名均得到正确保存名", async ({ page }) => {
  const { api } = await setupUser(page);
  const caseId = await createCase(api, "S12 案件");
  const evId = await createEvidence(api, caseId, "工资条", "入职时间：2022-10-01");

  // 引号由 _safe_filename 剥除，分号保留在 filename* 中并中性化在 ASCII 回退里。
  const specs: Array<{ name: string; expected: string }> = [
    { name: "March Bundle v2", expected: "材料包-March Bundle v2.pdf" },
    { name: 'Q1; "final" draft', expected: "材料包-Q1; final draft.pdf" },
  ];

  for (const spec of specs) {
    const pkgId = await createPackage(api, caseId, spec.name);
    await addItems(api, pkgId, [evId]);
    await createSnapshot(api, pkgId);
    const job = await apiJson<{ id: string }>(
      api,
      "post",
      `/material-packages/${pkgId}/exports`,
      { format: "pdf" });
    expect(job.status, JSON.stringify(job.body)).toBe(201);

    // 响应头：ASCII 回退必须合理非空、可 latin-1 编码。
    const dl = await api.get(`exports/${job.body.id}/download`);
    expect(dl.status()).toBe(200);
    const header = dl.headers()["content-disposition"] ?? "";
    expect(header).toContain("filename*=UTF-8''");
    const fallback = /filename="([^"]*)"/.exec(header)?.[1] ?? "";
    expect(fallback).toMatch(/^[\x20-\x7e]+$/);
    expect(fallback.replace(/[.\-_ ]/g, "")).not.toBe(""); // 不是 `-.pdf` 这类空壳

    // 浏览器真实保存名：filename* 解析链最终写入 a.download 的值。
    // （headless Chromium 对非 ASCII a.download 值会丢弃，suggestedFilename
    // 不可用；见 scenario 6 注释。）
    await page.goto(`/cases/${caseId}/material-packages/${pkgId}/export`);
    await installDownloadSpy(page);
    const record = page.locator("li.card").first();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      record.getByRole("button", { name: "下载" }).click(),
    ]);
    expect(await download.failure()).toBeNull();
    expect(await readDownloadName(page)).toBe(spec.expected);
  }
});

/**
 * Patch `HTMLAnchorElement.prototype.click` to record the filename
 * `downloadWithAuth` assigns to `a.download` — the string a real browser
 * would offer as the save name.
 */
async function installDownloadSpy(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __dlName?: string };
    const orig = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
      w.__dlName = this.download;
      return orig.call(this);
    };
  });
}

async function readDownloadName(page: Page): Promise<string> {
  return page.evaluate(() => (window as unknown as { __dlName?: string }).__dlName ?? "");
}

async function waitForEditPage(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: /保存草稿/ })).toBeVisible({ timeout: 15_000 });
}
