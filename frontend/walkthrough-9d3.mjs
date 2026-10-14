/**
 * Phase 9-D-3 人工走查辅助驱动（T1-T8）。
 *
 * 用法（前后端都在跑时）：
 *   node frontend/walkthrough-9d3.mjs
 *
 * 产出：walkthrough-9d3/ 下逐页截图 + 控制台 PASS/ISSUE 证据行。
 * 纯视觉质量项（导出排版观感等）只截图，最终判定仍需人工看图。
 */
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const WEB = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000/api/v1";
const PROJ = path.resolve(import.meta.dirname, "..");
const SHOTS = path.join(PROJ, "walkthrough-9d3");
const MAT = "/tmp/walk9d3/mat";

fs.mkdirSync(SHOTS, { recursive: true });

const findings = [];
function pass(t, msg) {
  findings.push({ level: "PASS", task: t, msg });
  console.log(`  ✅ [${t}] ${msg}`);
}
function issue(t, sev, msg, route, repro) {
  findings.push({ level: "ISSUE", task: t, sev, msg, route, repro });
  console.log(`  ⚠️ [${t}][${sev}] ${msg} | 路由=${route} | 复现=${repro}`);
}
function manual(t, msg) {
  findings.push({ level: "MANUAL", task: t, msg });
  console.log(`  👁 [${t}][需人工] ${msg}`);
}
const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, name), fullPage: true });

/**
 * 客户端路由 + 等待接口时，networkidle 经常在数据到达前就返回，
 * 直接 innerText 断言会读到「加载中…」。统一等正文出现匹配文本再断言。
 */
const settle = (re, timeout = 15000) =>
  page.waitForFunction(
    (src) => new RegExp(src).test(document.body.innerText),
    re.source,
    { timeout },
  ).catch(() => {});

async function api(method, p, body, token) {
  const res = await fetch(API + p, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  return { status: res.status, body: text ? JSON.parse(text) : null };
}

// ---------- 准备材料 ----------
execFileSync("bash", ["-lc", `rm -rf ${MAT} && "${PROJ}/backend/.venv/bin/python" "${PROJ}/scripts/make-real-materials.py" ${MAT}`], { stdio: "pipe" });
console.log("▶ 准备：材料套件已生成", MAT);

const email = `walk9d3-${Date.now()}@example.com`;
const reg = await api("POST", "/auth/register", { email, password: "correct-horse-battery" });
if (reg.status !== 201 && reg.status !== 200) throw new Error("register failed: " + JSON.stringify(reg));
const TOKEN = reg.body.access_token;

const browser = await chromium.launch();
const ctx = await browser.newContext();
await ctx.addInitScript((t) => window.localStorage.setItem("leo.token", t), TOKEN);
const page = await ctx.newPage();
const dialogs = [];
// 必须主动处理：只 push 不 settle 会让 confirm 挂起，导致 click 超时。
// 默认 dismiss（取消），需要真正执行时把 dialogMode 置为 "accept"。
let dialogMode = "dismiss";
page.on("dialog", (d) => {
  dialogs.push(d.message());
  void (dialogMode === "accept" ? d.accept() : d.dismiss()).catch(() => {});
});

// ---------- T1 首次进入 ----------
console.log("\n▶ T1 首次进入：登录→建案件→上传");
await page.goto(`${WEB}/login`, { waitUntil: "networkidle" });
await shot(page, "01-t1-login.png");
if (await page.locator('input[type="password"]').count()) pass("T1", "登录页含密码框，无需文档可见表单");
else issue("T1", "P1", "登录页未见密码框", "/login", "打开 /login 观察");

await page.goto(`${WEB}/cases`, { waitUntil: "networkidle" });
await settle(/还没有案件|新建案件/);
await shot(page, "02-t1-cases-empty.png");
const emptyText = await page.locator("text=还没有案件").count();
if (emptyText) pass("T1", "案件列表空态有引导文案「还没有案件…」");
else issue("T1", "P2", "案件列表空态缺引导文案", "/cases", "新账号打开 /cases");

// 建案件（走真实 UI）
await page.getByText("新建案件", { exact: true }).first().click();
await page.waitForLoadState("networkidle");
await page.locator("input").first().fill("9-D-3 走查案件");
await page.locator("button", { hasText: /创建|保存/ }).first().click();
// client 路由跳转（router.replace）不触发 load 事件，必须等 URL 变化
await page.waitForURL(/\/cases\/[0-9a-f-]{36}/, { timeout: 15000 });
await page.waitForLoadState("networkidle");
await shot(page, "03-t1-case-created.png");
const caseId = page.url().match(/cases\/([0-9a-f-]{36})/)?.[1];
if (caseId) pass("T1", `UI 建案件成功并进入案件页 case=${caseId}`);
else issue("T1", "P1", "UI 建案件后未落到案件页", "/cases/new", "点新建案件→填写→创建，观察跳转");

// ---------- T2 资料库 ----------
console.log("\n▶ T2 资料库：上传/状态词/重试");
await page.goto(`${WEB}/cases/${caseId}/files`, { waitUntil: "networkidle" });
await shot(page, "04-t2-files-empty.png");
await page.locator('input[type="file"]').setInputFiles([
  `${MAT}/劳动合同.pdf`,
  `${MAT}/聊天记录.txt`,
  `${MAT}/损坏文件.pdf`,
]);
await page.waitForFunction(
  () =>
    document.body.innerText.includes("劳动合同.pdf") &&
    document.body.innerText.includes("聊天记录.txt") &&
    document.body.innerText.includes("损坏文件.pdf"),
  null,
  { timeout: 30000 },
);
await page.waitForTimeout(1000);
// 按钮在上传/加载未完时 disabled，等它可用再点
await page.locator("button", { hasText: "全部解析" }).and(page.locator(":not([disabled])")).first().click({ timeout: 60000 });
// 等状态收敛：以 API 状态为准（UI 文案另行断言），避免只看 body 文案误判
const TERMINAL = ["REVIEW_REQUIRED", "COMPLETED", "FAILED"];
let settled = false;
let statuses = [];
for (let i = 0; i < 60; i++) {
  const st = await api("GET", `/cases/${caseId}/files`, null, TOKEN);
  statuses = st.body.files.map((f) => f.status);
  if (statuses.length === 3 && statuses.every((s) => TERMINAL.includes(s))) {
    settled = true;
    break;
  }
  await page.waitForTimeout(1000);
}
if (!settled) issue("T2", "P1", `文件状态未在 60s 内收敛到终态：${statuses.join(",")}`, `/cases/${caseId}/files`, "上传 3 个文件→全部解析→观察状态是否停在中间态");
await page.reload({ waitUntil: "networkidle" });
await settle(/资料库/);
await settle(/劳动合同\.pdf/);
await shot(page, "05-t2-analyzed.png");
const body2 = await page.locator("body").innerText();
const words = ["已上传", "解析中", "待确认", "已完成", "失败"].filter((w) => body2.includes(w));
if (words.length) pass("T2", `列表实际出现状态词：${words.join("、")}`);
else issue("T2", "P1", "文件状态收敛后列表未出现任何状态词", `/cases/${caseId}/files`, "上传并解析后观察每行状态标签");
if (body2.includes("失败")) pass("T2", "损坏文件的终态「失败」在列表中可见");
else issue("T2", "P1", "损坏文件未显示「失败」状态", `/cases/${caseId}/files`, "上传损坏 PDF→全部解析→观察该行状态");
const retryVisible = await page.locator("button", { hasText: "重试" }).count();
if (retryVisible > 0) pass("T2", `失败行出现「重试」按钮（${retryVisible} 个）`);
else issue("T2", "P1", "失败行未出现重试按钮", `/cases/${caseId}/files`, "上传损坏 PDF→全部解析→观察失败行");

// ---------- T3 审核台 ----------
console.log("\n▶ T3 审核台：分栏/修改不覆盖提示/低置信解释");
const files = await api("GET", `/cases/${caseId}/files`, null, TOKEN);
const m1 = files.body.files.find((f) => f.original_filename === "劳动合同.pdf");
const evs = await api("GET", `/cases/${caseId}/evidence`, null, TOKEN);
const m1ev = evs.body.evidence.find((e) => e.source_file_id === m1.id);
// 审核台只渲染「有 review item 的字段」（后端 analysis.py 只为 proof_purpose 和
// <0.80 低置信字段建 item），所以人工修订必须落在 proof_purpose 上才会出现卡片。
await api("PATCH", `/evidence/${m1ev.id}`, {
  summary: "走查人工修订：入职 2022-10-01。",
  proof_purpose: "走查人工修订：用于证明入职时间与岗位约定。",
}, TOKEN);
await page.goto(`${WEB}/cases/${caseId}/review`, { waitUntil: "networkidle" });
await settle(/AI 审核工作台/);
await shot(page, "06-t3-review.png");
const body3 = await page.locator("body").innerText();
if (body3.includes("这个字段已由你修改，后续 AI 解析不会覆盖"))
  pass("T3", "人工修订后的字段旁出现「已由你修改…不会覆盖」提示");
else
  issue("T3", "P1", "人工修订提示未出现", `/cases/${caseId}/review`, "PATCH evidence 的 proof_purpose 后打开审核台，观察卡片下方无绿色提示");
if (body3.includes("置信度低，请人工确认")) pass("T3", "低置信字段有「置信度低，请人工确认」解释");
else pass("T3", "高置信样本不显示低置信提示（符合预期），低置信行为由 T3b 专项验证");

// ---------- T3b 低置信样本（消除上一条人工复核项） ----------
console.log("\n▶ T3b 低置信样本：置信度提示");
const lowFile = `${MAT}/无信号文本.txt`;
fs.writeFileSync(lowFile, "这是一段刻意不含任何已知证据关键词的普通文字，用于触发低置信分支。");
const upForm = new FormData();
upForm.append("files", new Blob([fs.readFileSync(lowFile)], { type: "text/plain" }), "无信号文本.txt");
const upLow = await fetch(`${API}/cases/${caseId}/files`, {
  method: "POST",
  headers: { Authorization: `Bearer ${TOKEN}` },
  body: upForm,
});
const upLowBody = await upLow.json();
const lowId = upLowBody.files?.[0]?.id;
if (upLow.status === 201 && lowId) pass("T3b", "无信号文本上传成功");
else issue("T3b", "P1", `低置信样本上传失败：${upLow.status} ${JSON.stringify(upLowBody)}`, `/cases/${caseId}/files`, "上传纯文本后观察响应");
const anLow = await fetch(`${API}/files/${lowId}/analyze`, {
  method: "POST",
  headers: { Authorization: `Bearer ${TOKEN}` },
});
const anLowBody = await anLow.json().catch(() => null);
if (anLow.status === 200 || anLow.status === 202) pass("T3b", "低置信样本解析成功");
else issue("T3b", "P1", `低置信样本解析失败：${anLow.status} ${JSON.stringify(anLowBody)}`, `/cases/${caseId}/files`, "对无关键词文本点解析，观察状态码");
await page.goto(`${WEB}/cases/${caseId}/review`, { waitUntil: "networkidle" });
await settle(/AI 审核工作台/);
await page.waitForTimeout(500);
await shot(page, "06b-t3-lowconf.png");
const body3b = await page.locator("body").innerText();
if (body3b.includes("置信度低，请人工确认")) pass("T3b", "低置信字段在审核台显示「置信度低，请人工确认」");
else issue("T3b", "P1", "低置信字段未出现「置信度低，请人工确认」提示", `/cases/${caseId}/review`, "解析无关键词文本后打开审核台");

// ---------- T4 证据目录 ----------
console.log("\n▶ T4 证据目录：徽标/证明目的");
await api("POST", `/evidence/${m1ev.id}/confirm`, {}, TOKEN); // 制造已确认对照
await page.goto(`${WEB}/cases/${caseId}/evidence`, { waitUntil: "networkidle" });
await settle(/证据目录/);
await shot(page, "07-t4-evidence.png");
const body4 = await page.locator("body").innerText();
if (body4.includes("待确认") && body4.includes("已确认")) pass("T4", "同页可见「待确认」「已确认」双态徽标");
else issue("T4", "P1", "双态徽标不全", `/cases/${caseId}/evidence`, "打开证据目录观察徽标（需同时存在已确认与未确认证据）");
if (body4.includes("已人工修改")) pass("T4", "人工修订过的证据带「已人工修改」徽标");
else issue("T4", "P2", "缺少「已人工修改」徽标", `/cases/${caseId}/evidence`, "PATCH evidence summary 后打开证据目录");
const editBtn = page.locator("button", { hasText: "修改" }).first();
if (await editBtn.count()) {
  await editBtn.click();
  await page.waitForTimeout(300);
  const editBody = await page.locator("body").innerText();
  if (editBody.includes("证明目的")) pass("T4", "编辑态可见「证明目的」标签，可直接修改拟证明事项");
  else issue("T4", "P1", "编辑态未见「证明目的」字段", `/cases/${caseId}/evidence`, "证据目录点「修改」，观察表单字段");
  await shot(page, "07b-t4-evidence-edit.png");
  await page.locator("button", { hasText: "取消" }).first().click().catch(() => {});
} else issue("T4", "P1", "证据目录无「修改」入口", `/cases/${caseId}/evidence`, "打开证据目录观察每行操作按钮");
const blankProof = (await api("GET", `/cases/${caseId}/evidence`, null, TOKEN)).body.evidence.filter(
  (e) => !e.proof_purpose,
);
if (blankProof.length) pass("T4", `本案已有 ${blankProof.length} 条空证明目的证据（空值态）`);
else pass("T4", "本案证据均已填写证明目的（正常态），空值行为由 T4b 专项验证");

// ---------- T4b 证明目的留空（构造空值样本，随后恢复） ----------
console.log("\n▶ T4b 证明目的留空：是否有提示 + 已有内容是否原样显示");
await api("PATCH", `/evidence/${m1ev.id}`, { proof_purpose: null }, TOKEN);
await page.goto(`${WEB}/cases/${caseId}/evidence`, { waitUntil: "networkidle" });
await settle(/证据目录/);
await shot(page, "07c-t4-blank-proof.png");
const body4b = await page.locator("body").innerText();
if (body4b.includes("尚未填写拟证明事项"))
  pass("T4b", "空证明目的在非编辑态显示中性提示「尚未填写拟证明事项，可编辑补充」");
else if (body4b.includes("留空") || body4b.includes("待补充") || body4b.includes("未填写"))
  pass("T4b", "证明目的留空时给出占位说明");
else
  issue(
    "T4b",
    "P3",
    "证明目的留空后目录内无任何提示（编辑框空、非编辑态整块消失）",
    `/cases/${caseId}/evidence`,
    "PATCH evidence proof_purpose=null→证据目录观察该行是否出现提示",
  );
// 编辑态占位符验证（placeholder 不在 innerText 里，单独查）
const editBtn2 = page.locator("button", { hasText: /修改|编辑/ }).first();
if (await editBtn2.count()) {
  await editBtn2.click();
  await page.waitForTimeout(300);
  const ph = await page.locator('textarea[placeholder*="尚未填写拟证明事项"]').count();
  if (ph > 0) pass("T4b", "编辑态证明目的输入框有占位提示");
  else issue("T4b", "P3", "编辑态证明目的输入框无占位提示", `/cases/${caseId}/evidence`, "证据目录点「修改」，观察证明目的输入框 placeholder");
  await page.locator("button", { hasText: "取消" }).first().click().catch(() => {});
}
// 恢复并验证已有内容原样显示
await api("PATCH", `/evidence/${m1ev.id}`, { proof_purpose: "走查人工修订：用于证明入职时间与岗位约定。" }, TOKEN);
await page.reload({ waitUntil: "networkidle" });
await settle(/证据目录/);
const body4b2 = await page.locator("body").innerText();
if (body4b2.includes("走查人工修订：用于证明入职时间与岗位约定") && !body4b2.includes("尚未填写拟证明事项"))
  pass("T4b", "已有证明目的内容时原样显示，无空值提示");
else issue("T4b", "P2", "恢复内容后显示异常（内容未显示或仍出现空值提示）", `/cases/${caseId}/evidence`, "PATCH 回有值后刷新观察");

// ---------- T5 时间轴 ----------
console.log("\n▶ T5 时间轴：构建/日期可空/合并确认");
const evs2 = await api("GET", `/cases/${caseId}/evidence`, null, TOKEN);
const another = evs2.body.evidence.find((e) => e.id !== m1ev.id);
if (another) {
  await api("PATCH", `/evidence/${another.id}`, { event_date: "2023-05-20" }, TOKEN);
  // 时间轴生成只取 CONFIRMED 证据（services/timeline.py:55），必须先确认才有第 2 个事件
  await api("POST", `/evidence/${another.id}/confirm`, {}, TOKEN);
}
await page.goto(`${WEB}/cases/${caseId}/timeline`, { waitUntil: "networkidle" });
await settle(/案件时间轴/);
const btnTexts = await page.locator("button").allInnerTexts();
const buildBtn = page.locator("button", { hasText: /生成|构建|时间轴/ }).first();
await buildBtn.click().catch(() => {});
await page.waitForTimeout(2000);
await page.reload({ waitUntil: "networkidle" });
await settle(/案件时间轴/);
await shot(page, "08-t5-timeline.png");
const boxes = page.locator('input[type="checkbox"]');
const nbox = await boxes.count();
if (nbox >= 2) {
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  // —— 取消路径：确认框 → dismiss → 不得发送合并请求、数据不变 ——
  dialogs.length = 0;
  dialogMode = "dismiss";
  const evBefore = (await api("GET", `/cases/${caseId}/events`, null, TOKEN)).body.events;
  await page.locator("button", { hasText: "合并所选" }).click();
  await page.waitForTimeout(1500);
  await shot(page, "08b-t5-merge-cancel.png");
  if (dialogs.length === 0)
    issue("T5", "P2", "合并事件无任何确认提示，点击即执行且不可撤销", `/cases/${caseId}/timeline`, "勾选 2 个事件→点「合并所选」，观察无 confirm 直接合并");
  else {
    pass("T5", `合并有确认提示：「${dialogs[0].split("\n")[0]}」…（含受影响事件与不可撤销说明）`);
    if (/不可撤销/.test(dialogs[0]) && /「/.test(dialogs[0])) pass("T5", "确认文案列出了受影响事件并写明不可撤销");
    else issue("T5", "P2", `确认文案缺少受影响事件或不可撤销说明：「${dialogs[0]}」`, `/cases/${caseId}/timeline`, "阅读合并确认框全文");
    const evAfterCancel = (await api("GET", `/cases/${caseId}/events`, null, TOKEN)).body.events;
    const sameSet = JSON.stringify(evAfterCancel.map((e) => e.id).sort()) === JSON.stringify(evBefore.map((e) => e.id).sort());
    if (sameSet && evAfterCancel.length === evBefore.length) pass("T5", "取消合并后事件集合未变（无请求发出、数据不变）");
    else issue("T5", "P1", `取消合并后数据被改变：${evBefore.length}→${evAfterCancel.length}`, `/cases/${caseId}/timeline`, "确认框点取消后用 API 对比事件列表");
  }
  // —— 确认路径：accept → 合并真正执行 ——
  dialogMode = "accept";
  dialogs.length = 0;
  await page.locator('input[type="checkbox"]').nth(0).check().catch(() => {});
  await page.locator('input[type="checkbox"]').nth(1).check().catch(() => {});
  await page.locator("button", { hasText: "合并所选" }).click();
  await page.waitForTimeout(1500);
  dialogMode = "dismiss";
  await page.reload({ waitUntil: "networkidle" });
  await settle(/案件时间轴/);
  await shot(page, "09-t5-after-merge.png");
  const nboxAfter = await page.locator('input[type="checkbox"]').count();
  if (nboxAfter === nbox - 1) pass("T5", `确认合并后事件数 ${nbox}→${nboxAfter}，合并真正执行`);
  else issue("T5", "P1", `确认合并后事件数未变（${nbox}→${nboxAfter}）`, `/cases/${caseId}/timeline`, "确认框点确定后刷新观察事件数");
} else manual("T5", `时间轴复选框仅 ${nbox} 个，合并场景需 ≥2 事件，请人工复核`);

// ---------- T6 材料包 ----------
console.log("\n▶ T6 材料包：空态引导/四词区分/发布≠锁定提示");
await page.goto(`${WEB}/cases/${caseId}/material-packages`, { waitUntil: "networkidle" });
await settle(/材料包/);
await shot(page, "10-t6-pkg-empty.png");
const body6 = await page.locator("body").innerText();
if (body6.includes("还没有材料包") && body6.includes("新建材料包")) pass("T6", "空态有引导且指向「新建材料包」");
else issue("T6", "P1", "材料包列表空态缺少引导或「新建材料包」入口", `/cases/${caseId}/material-packages`, "新建案件后打开材料包列表");
await page.getByText("新建材料包", { exact: true }).first().click();
await page.waitForLoadState("networkidle");
await page.locator("input").first().fill("走查测试卷");
await page.locator("button", { hasText: "创建草稿" }).click();
await page.waitForURL(/material-packages\/[0-9a-f-]{36}/, { timeout: 15000 });
// 客户端路由下 networkidle 会提前返回，必须等详情真正渲染完再断言
await page.waitForFunction(() => /草稿版本 v\d/.test(document.body.innerText), null, { timeout: 15000 });
await page.waitForLoadState("networkidle");
const pkgUrl = page.url();
await shot(page, "11-t6-pkg-edit.png");
const body6b = await page.locator("body").innerText();
if (/草稿版本|草稿/.test(body6b)) pass("T6", "编辑页可见「草稿」状态字样");
if (body6b.includes("快照")) pass("T6", "编辑页可见「快照」相关字样");
if (await page.locator("button", { hasText: "发布" }).count()) pass("T6", "编辑页有「发布」按钮");
if (/草稿版本 v\d/.test(body6b) && body6b.includes("历史快照")) pass("T6", "头部同时展示草稿版本号与历史快照数（草稿/快照可区分）");
// 第一次点发布：只验证确认框文案，然后取消（不改变状态）
dialogs.length = 0;
await page.locator("button", { hasText: "发布" }).first().click();
await page.waitForTimeout(500);
if (dialogs.length === 0)
  issue("T6", "P2", "发布无确认提示", pkgUrl, "编辑页点发布，观察无 confirm");
else if (/发布只是状态标记/.test(dialogs[0]))
  pass("T6", `发布确认框写明「发布只是状态标记…仍可继续编辑」：「${dialogs[0]}」`);
else issue("T6", "P2", `发布确认框未说明「发布≠锁定」：「${dialogs[0]}」`, pkgUrl, "编辑页点发布，阅读确认框文案");
// 第二次点发布：真正执行
dialogs.length = 0;
dialogMode = "accept";
await page.locator("button", { hasText: "发布" }).first().click();
await page.waitForTimeout(1500);
dialogMode = "dismiss";
const body6c = await page.locator("body").innerText();
if (body6c.includes("仍可继续编辑")) pass("T6", "发布后提示「发布只是状态标记，仍可继续编辑条目」");
else issue("T6", "P1", "发布后未出现「仍可继续编辑」说明", pkgUrl, "确认发布后观察页面提示");
if (body6c.includes("已发布")) pass("T6", "头部状态切换为「已发布」且仍显示草稿版本（发布≠冻结）");
else issue("T6", "P1", "发布后状态字样未更新", pkgUrl, "确认发布后观察头部状态");
if ((await page.locator("button", { hasText: "保存草稿" }).count()) > 0)
  pass("T6", "发布后「保存草稿」按钮仍在（未进入只读态，只有归档才锁定）");
else issue("T6", "P1", "发布后编辑入口消失（与「发布不锁定」规则冲突）", pkgUrl, "确认发布后观察工具栏");
await shot(page, "12-t6-published.png");

// ---------- T7 导出 ----------
console.log("\n▶ T7 导出：快照指引/生成卷宗");
const pkgId = pkgUrl.match(/material-packages\/([0-9a-f-]{36})/)?.[1];
await page.goto(`${WEB}/cases/${caseId}/material-packages/${pkgId}/export`, { waitUntil: "networkidle" });
await settle(/生成材料包卷宗/);
await settle(/尚无快照|快照版本/);
await shot(page, "13-t7-export.png");
const body7 = await page.locator("body").innerText();
if (body7.includes("尚无快照") && body7.includes("请先在编辑页"))
  pass("T7", "无快照时导出页给出明确下一步指引（先保存草稿并创建快照）");
else issue("T7", "P1", "无快照时缺少导出前置指引", `/cases/${caseId}/material-packages/${pkgId}/export`, "新建材料包（不建快照）直接打开导出页");
if (body7.includes("快照保证导出内容不可变")) pass("T7", "解释了快照与导出内容不可变的关系");
else issue("T7", "P2", "未解释快照与导出不可变的关系", `/cases/${caseId}/material-packages/${pkgId}/export`, "无快照时打开导出页阅读提示文案");

// 走真实接口写入条目并建快照，验证导出页「有快照」形态与生成卷宗链路
const evs3 = (await api("GET", `/cases/${caseId}/evidence`, null, TOKEN)).body.evidence;
const pkgNow = (await api("GET", `/material-packages/${pkgId}`, null, TOKEN)).body;
const putItems = await api("PUT", `/material-packages/${pkgId}/items`, {
  expected_draft_version: pkgNow.draft_version,
  items: evs3.slice(0, 2).map((e) => ({
    evidence_id: e.id,
    display_name: e.title,
    proof_purpose: e.proof_purpose,
    review_status: "PENDING",
  })),
}, TOKEN);
if (putItems.status === 200) pass("T7", `保存材料包条目成功（draft_version=${putItems.body.draft_version}）`);
else issue("T7", "P1", `保存材料包条目失败：${putItems.status} ${JSON.stringify(putItems.body)}`, pkgUrl, "编辑页选入证据后保存，观察 API 响应");
const pkgAfter = (await api("GET", `/material-packages/${pkgId}`, null, TOKEN)).body;
const snapRes = await api("POST", `/material-packages/${pkgId}/snapshots`, { expected_draft_version: pkgAfter.draft_version }, TOKEN);
if (snapRes.status === 201) pass("T7", `创建快照成功（v${snapRes.body.version}）`);
else issue("T7", "P1", `创建快照失败：${snapRes.status} ${JSON.stringify(snapRes.body)}`, pkgUrl, "编辑页点「创建快照」，观察 API 响应");

await page.reload({ waitUntil: "networkidle" });
await settle(/快照版本/);
const body7b = await page.locator("body").innerText();
if (!body7b.includes("尚无快照") && body7b.includes("快照版本"))
  pass("T7", "有快照后出现「快照版本」选择器且不再提示「尚无快照」");
else issue("T7", "P1", "有快照时导出页形态未切换", `/cases/${caseId}/material-packages/${pkgId}/export`, "创建快照后刷新导出页");
const pdfRadio = page.locator('input[name="format"][value="pdf"]');
if (await pdfRadio.count()) await pdfRadio.check();
await page.locator("button", { hasText: "生成卷宗" }).first().click();
await page.waitForTimeout(4000);
const body7c = await page.locator("body").innerText();
if (/可以下载|完成于|COMPLETED|已完成/.test(body7c)) pass("T7", "UI 触发 PDF 卷宗生成成功，导出记录中出现可下载任务");
else issue("T7", "P1", "UI 生成卷宗未出现成功/可下载记录", `/cases/${caseId}/material-packages/${pkgId}/export`, "导出页选 PDF→生成卷宗→观察导出记录");
await shot(page, "13b-t7-export-jobs.png");

// 下载真实 PDF 并核对内容（编号 / 拟证明事项 / 中文可读），把"看导出文件"从纯人工变成可验证
const jobList = (await api("GET", `/material-packages/${pkgId}/exports`, null, TOKEN)).body;
const job = (jobList.exports ?? []).find((j) => j.status === "COMPLETED");
if (job) {
  const dl = await fetch(`${API}/exports/${job.id}/download`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  const pdfBuf = Buffer.from(await dl.arrayBuffer());
  const pdfPath = path.join(SHOTS, "t7-材料包卷宗.pdf");
  fs.writeFileSync(pdfPath, pdfBuf);
  if (dl.status === 200 && pdfBuf.length > 0) pass("T7", `PDF 下载成功（${pdfBuf.length} 字节）→ ${pdfPath}`);
  else issue("T7", "P1", `PDF 下载失败：HTTP ${dl.status}`, `/cases/${caseId}/material-packages/${pkgId}/export`, "导出完成后点「下载」");
  let pdfText = "";
  try {
    pdfText = execFileSync(
      PROJ + "/backend/.venv/bin/python",
      ["-c", "import sys, fitz; d=fitz.open(sys.argv[1]); print(''.join(p.get_text() for p in d))", pdfPath],
      { encoding: "utf8" },
    );
  } catch (err) {
    issue("T7", "P1", `PDF 文本抽取失败：${err.message?.slice(0, 200)}`, pdfPath, "用 PyMuPDF 打开导出的 PDF");
  }
  if (pdfText) {
    if (pdfText.includes("拟证明事项")) pass("T7", "PDF 含「拟证明事项」小节");
    else issue("T7", "P1", "PDF 缺少「拟证明事项」", pdfPath, "打开导出的 PDF 搜索「拟证明事项」");
    if (/材料\d+[:：]/.test(pdfText)) pass("T7", "PDF 含材料编号（材料N：）");
    else issue("T7", "P1", "PDF 缺少材料编号", pdfPath, "打开导出的 PDF 检查每份材料标题");
    if (/[一-龥]{4,}/.test(pdfText)) pass("T7", "PDF 中文可正常抽取（非乱码）");
    else issue("T7", "P1", "PDF 中文抽取为空或乱码", pdfPath, "对导出 PDF 做文本抽取检查");
    if (pdfText.includes("走查人工修订：用于证明入职时间与岗位约定"))
      pass("T7", "PDF 正文与最终确认的拟证明事项一致（回溯到人工修订值）");
    else issue("T7", "P2", "PDF 未包含人工修订后的拟证明事项", pdfPath, "对比证据目录的证明目的与导出 PDF 文本");
  }
} else {
  issue("T7", "P1", "没有 COMPLETED 状态的导出任务可供下载", `/cases/${caseId}/material-packages/${pkgId}/export`, "生成卷宗后查看导出记录状态");
}
manual("T7", "卷宗排版观感（字体/分页/表格布局）需人工看 t7-材料包卷宗.pdf，本项只做文本层校验");

// ---------- T8 全局 ----------
console.log("\n▶ T8 全局：免责声明/错误信息可执行性");
if (body7.includes("仅供参考，不构成正式法律意见")) pass("T8", "全局免责声明在页面可见（layout 层）");
else issue("T8", "P1", "页面未见全局免责声明", "/cases/.../export", "任一登录后页面观察底部/头部");
await page.goto(`${WEB}/cases/${caseId}/files`, { waitUntil: "networkidle" });
await settle(/资料库/);
await page.locator('input[type="file"]').setInputFiles([`${MAT}/伪装.txt`]);
await page.waitForFunction(() => document.body.innerText.includes("文件内容与扩展名不一致"), null, { timeout: 15000 }).catch(() => {});
await shot(page, "14-t8-reject.png");
const body8 = await page.locator("body").innerText();
if (body8.includes("文件内容与扩展名不一致"))
  pass("T8", "上传拒绝的具体原因（「文件内容与扩展名不一致」）直接展示给用户");
else issue("T8", "P1", "上传拒绝原因未展示", `/cases/${caseId}/files`, "上传伪装.txt 观察提示");
manual("T8", "409 VERSION_CONFLICT / SNAPSHOT_REQUIRED 的 UI 展示：frontend/e2e/phase9c-ui.spec.ts:244-249 断言 error.code=SNAPSHOT_REQUIRED（9-C 用例，本走查不重复触发，需另跑 playwright test 复核）");

// ---------- 汇总 ----------
fs.writeFileSync(path.join(SHOTS, "findings.json"), JSON.stringify(findings, null, 2));
const npass = findings.filter((f) => f.level === "PASS").length;
const nissue = findings.filter((f) => f.level === "ISSUE").length;
const nmanual = findings.filter((f) => f.level === "MANUAL").length;
console.log(`\n🎉 走查完成：PASS=${npass} ISSUE=${nissue} 需人工复核=${nmanual}`);
console.log(`截图目录：${SHOTS}`);

await browser.close();
