# Phase 9-D-3 人工走查记录

执行日期：2026-10-13　范围：`docs/16` §4 清单 T1-T8（含 T3b/T4b 两个专项补测）　性质：只报有依据问题，不改业务规则。

- 走查驱动：`frontend/walkthrough-9d3.mjs`（浏览器真实操作 + 截图 + 结构化结论）
- 结论文件：`walkthrough-9d3/findings.json`（41 条：PASS=37，ISSUE=2，MANUAL=2）
- 证据目录：`walkthrough-9d3/`（19 张截图 + `t7-材料包卷宗.pdf`）
- 走查案件：`d767e9c9-c5eb-4f02-bd9b-92108598334a`（最后一轮）

---

## 1. 环境恢复记录（容器重建导致，先修复再走查）

容器在 10-13 13:36 重建，`Dockerfile` 的 `BACKUP_EXCLUDES` 排除 `*/.venv`、`*/node_modules`，
且镜像本身不含 PostgreSQL，因此走查前环境不可用。恢复步骤与结果：

| # | 缺失/缺陷 | 处理 | 结果 |
|---|---|---|---|
| E1 | Python venv、前端 node_modules、PostgreSQL 全部丢失 | `apt-get install postgresql-15` + `pg_ctlcluster 15 main start`；建 `leo` 角色与 `labor_evidence`/`labor_evidence_test`；`python3 -m venv .venv && pip install -r requirements.txt`；`npm install`；`alembic upgrade head`（5 个迁移到 `7b2e9d41c05f`） | 后端 `{"status":"ok"}`，前端 HTTP 200 |
| E2 | **容器 locale 损坏**（`locale` 报 `Cannot set LC_CTYPE`，`en_US.UTF-8` 未生成）→ Playwright `setInputFiles` 对**中文路径静默丢文件**（`el.files.length===0`，无报错、无请求），走查在 T2 卡死 | `apt-get install locales && locale-gen en_US.UTF-8` | 同一脚本重跑通过；**仅影响 Playwright 按路径上传非 ASCII 文件名**，`curl` 类 e2e 脚本不受影响 |
| E3 | `requirements.txt` 缺 `email-validator`，README「快速开始」装完依赖 `import app.main` 直接 `ImportError` | 补 `email-validator>=2.0` | 新建 `/tmp/venv-repro` 全新安装 → `import app.main` 打印 `IMPORT_OK` |

> E2 建议登记为新风险 R13（镜像未安装 `locales` → 走查/CI 上传中文文件名会假失败），留待 9-D-5 并入风险登记册。

---

## 2. 走查矩阵（T1-T8）

| 项 | 结论 | 证据 |
|---|---|---|
| T1 首次进入 | **通过**（3/3）：登录页含密码框；空案件列表有「还没有案件」引导；UI 建案件落到案件详情 | `01/02/03-*.png` |
| T2 资料库 | **通过**（3/3）：上传 3 份（合法 2 + 损坏 1）状态收敛到终态且列表出现「已完成/失败」；损坏文件显「失败」；失败行有「重试」 | `04-t2-files-empty.png`、`05-t2-analyzed.png` |
| T3 审核台 | **通过**：人工修订 `proof_purpose` 后出现「这个字段已由你修改，后续 AI 解析不会覆盖。」；高置信样本不显示低置信提示（符合预期） | `06-t3-review.png` |
| T3b 低置信样本 | **通过**（专项补测）：上传无关键词文本 → 解析 → 审核台出现「置信度低，请人工确认」 | `06b-t3-lowconf.png` |
| T4 证据目录 | **通过**（4/4）：同页「待确认/已确认」双态徽标；「已人工修改」徽标；编辑态可见「证明目的」标签可改 | `07-t4-evidence.png`、`07b-t4-evidence-edit.png` |
| T4b 证明目的留空 | **问题 P3**（见 §3-1） | `07c-t4-blank-proof.png` |
| T5 时间轴 | **问题 P2**（见 §3-2）；日期可空文案「日期（可空）」可见 | `08-t5-timeline.png`、`09-t5-after-merge.png` |
| T6 材料包 | **通过**（9/9）：空态引导→新建；编辑页「草稿」字样、「快照」相关字样、发布按钮；头部「草稿 · 草稿版本 v1 · 历史快照 0 个」四词可区分；发布确认框写明「发布只是状态标记，发布后仍可继续编辑条目」；发布后提示仍可编辑；状态变「已发布」且仍显示草稿版本；「保存草稿」按钮仍在（发布≠只读） | `10/11/12-*.png` |
| T7 导出 | **通过**（8/8，含真实下载校验）：无快照时指引「尚无快照。请先在编辑页保存草稿并创建快照后再导出（快照保证导出内容不可变）」；写入条目→建快照 v1→出现「快照版本」选择器；UI 生成 PDF 卷宗成功；**下载 5617 字节 PDF 并文本抽取校验**：含「拟证明事项」、含「材料N：」、中文非乱码、正文与人工修订后的拟证明事项一致 | `13-t7-export.png`、`13b-t7-export-jobs.png`、`t7-材料包卷宗.pdf` |
| T8 全局 | **通过**（2/2）：全局免责声明「仅供参考，不构成正式法律意见」可见；上传伪装文件直接展示原因「文件内容与扩展名不一致」 | `14-t8-reject.png` |

---

## 3. 发现的问题（有依据，附路由/复现/代码位置）

### 3.1 P3　证明目的留空后目录内没有任何后果提示

- 路由：`/cases/{id}/evidence`
- 复现：`PATCH /evidence/{id}` body `{"proof_purpose": null}` → 打开证据目录 → 点「修改」
- 现象：编辑框为空、周围无任何说明；非编辑态整块 `proof_purpose` 渲染消失（`evidence/page.tsx` 中 `row.proof_purpose && <p>…`），用户看不到留空会影响什么
- 影响：导出时才暴露（案件导出显示「（待补充）」`services/export.py:104`，材料包 PDF 显示「（未填写）」`services/export.py:736`）；材料包编辑页有占位说明「拟证明事项（留空则沿用证据原文）」（`edit/page.tsx:512`），证据目录没有对应说明
- 严重度：P3（不阻断流程，信息在下游才出现）
- 证据：`07c-t4-blank-proof.png`、`findings.json` 中 `T4b`

### 3.2 P2　时间轴合并无确认提示，点击即不可逆执行

- 路由：`/cases/{id}/timeline`
- 复现：勾选 2 个事件 → 点「合并所选（2）」→ 无任何 confirm，直接合并
- 代码：`frontend/src/app/cases/[id]/timeline/page.tsx:100` `merge()` 没有 `window.confirm`（同文件 `:90` 删除事件有 confirm）；后端 `services/timeline.py` 合并后 `survivor.review_status="CONFIRMED"`，合并不可撤销
- 影响：误触即丢失事件拆分关系，与「删除有确认」的既有交互约定不一致
- 严重度：P2
- 证据：`09-t5-after-merge.png`、`findings.json` 中 `T5`

> 两条均未修改代码（9-D-3 只产出问题清单），是否修复待你决定。

---

## 4. 走查脚本本身的修正（避免误判为产品缺陷）

以下为**脚本/环境**问题，已修复，不属于产品缺陷，列出以免后续误读：

1. `page.on("dialog")` 只 push 不 `dismiss()` → `confirm` 挂起导致点击超时（T6 卡死）；改为可切换的 `dialogMode`，先取消验证文案、再接受验证状态。
2. T2 只传 1 份可解析材料 → 目录只有 1 条证据，凑不出双态徽标与第 2 个时间轴事件；改为传 3 份（合法 2 + 损坏 1），并在生成时间轴前先确认第二条证据（`services/timeline.py:55` 只取 `CONFIRMED`）。
3. T3 原来修订 `summary`，但审核台只渲染有 review item 的字段（后端 `analysis.py:203` 只为 `proof_purpose` 与 <0.80 字段建 item），提示永远不会出现；改为同时修订 `proof_purpose`。
4. 客户端路由下 `networkidle` 提前返回 → 断言读到「加载中…」，出现假失败（T7 曾报 3 条假 P1）；统一加 `settle(正则)` 等正文渲染完成。
5. 导出任务列表键名是 `exports` 而非 `jobs`；已改正后拿到 `COMPLETED` 任务并真实下载。
6. 环境 E2（中文路径上传失败）与 E3（依赖缺失）属环境缺陷，见 §1。

---

## 5. 回归测试：命令与真实结果

| 命令 | 结果 |
|---|---|
| `cd backend && .venv/bin/pytest` | **270 passed**, 2 warnings, 186.96s |
| `cd frontend && npm run lint` | exit 0（`--max-warnings=0`） |
| `cd frontend && npm run typecheck` | exit 0 |
| `cd frontend && npm run test`（vitest） | **3 files / 22 tests passed** |
| `cd frontend && npx playwright test`（9-C 12 场景） | **12 passed** (55.5s)，含 `8. 无快照时导出页给出创建快照引导`（断言 `error.code=SNAPSHOT_REQUIRED`）、`9. 案件导出中心下载携带鉴权`、`12. 下载文件名兼容` |
| `bash scripts/e2e-real-materials.sh`（9-D-2） | **全部通过**：M1-M12 材料矩阵 + M1 七跳可追溯链 + mock OCR 空文本固化 |
| `bash scripts/e2e-smoke.sh` | **全流程通过**：上传→解析→核对→时间轴→导出→下载→A3 缺口 |
| `bash scripts/e2e-material-packages.sh` | **14 步全部通过**（含快照只读、冲突防护、越权 404、5 条前端路由 200） |
| `cd backend && .venv/bin/alembic check` | `No new upgrade operations detected.`（head=`7b2e9d41c05f`） |
| `node frontend/walkthrough-9d3.mjs` | **PASS=37 / ISSUE=2 / MANUAL=2** |

未在本阶段执行：`npm run build`（`next build` 与运行中的 `next dev` 共用 `.next`，留到 9-D-5 收尾时停服后跑）。

---

## 6. 仍未验证 / 需人工的项

| 项 | 状态 | 说明 |
|---|---|---|
| 卷宗排版观感（字体、分页、表格布局） | **未验证（需人工看图/看 PDF）** | 文本层已自动校验（编号、拟证明事项、中文非乱码、与人工修订值一致），版式观感未判定；文件：`walkthrough-9d3/t7-材料包卷宗.pdf` |
| 409 `VERSION_CONFLICT` 的 UI 文案实际展示 | **半验证** | 后端断言已跑（`tests/test_material_packages.py:409/423`，含在 270 passed 内）；前端渲染路径 `edit/page.tsx:183→375` 仅代码检查，本轮未在浏览器里真实触发并发冲突 |
| 409 `SNAPSHOT_REQUIRED` 的 UI 展示 | **已由自动化测试实测** | `e2e/phase9c-ui.spec.ts:244-249`（本轮 12 passed） |
| 证明目的留空在**导出文件**中的呈现 | 仅代码检查 | `export.py:104/736` 显示（待补充）/（未填写），未在本轮导出中构造空值样本 |

---

## 7. 9-D-3 DoD 判定

| DoD（`docs/16` §7） | 判定 |
|---|---|
| T1-T8 每项有「通过/问题」结论 | **满足**（矩阵见 §2，含 T3b/T4b 补测） |
| 每个问题附路由 + 复现步骤 + 严重度 | **满足**（§3，2 条） |
| 无「感觉不好」类无依据项 | **满足**（2 条问题均有代码位置与截图） |

**结论：9-D-3 走查完成，可进入 9-D-4（部署风险处置，需你批准）或先修复 §3 两条问题。**

---

## 8. 9-D-3a 修复（两个走查问题）

授权：用户 2026-10-13 指令「先完成 9-D-3a 和 9-D-3b」。仅修问题，不改数据结构与业务规则。

### 8.1 P2 时间轴合并无确认（已修）

- 改动：`frontend/src/lib/timeline-ui.ts`（新增纯函数 `buildMergeConfirmMessage`）+
  `frontend/src/app/cases/[id]/timeline/page.tsx`（`merge()` 在发请求前 `window.confirm`，
  取消则直接 return，不发任何请求）。
- 确认文案列出每个受影响事件（标题+日期）+ 合并后果（保留最早、其余标记已合并、
  证据关联转移）+ **不可撤销**说明。
- 单测：`frontend/src/lib/timeline-ui.test.ts`（1 例）。
- 浏览器复验（`walkthrough-9d3.mjs` T5）：
  - 取消路径：确认框出现 → dismiss → **API 事件集合逐 id 对比未变**（无请求发出）。
  - 确认路径：accept → `POST /events/merge` → 刷新后事件数 2→1。
- 顺带发现并修复**后端真实缺陷**：`routes/timeline.py` 的 merge 端点**从未 `db.commit()`**
  （`get_db` 的 `finally: db.close()` 在生产会回滚），此前单测通过是因为
  conftest 的共享 session 在请求间不关闭、事务一直开着。已补 `db.commit()` + `db.refresh(survivor)`，
  并新增回归测试 `test_merge_is_committed_to_database`（用**独立 session** 查询验证已提交）。

### 8.2 P3 证明目的留空无提示（已修）

- 改动：`frontend/src/app/cases/[id]/evidence/page.tsx`：
  - 非编辑态空值显示中性提示「尚未填写拟证明事项，可编辑补充」+「编辑」快捷入口；
  - 编辑态 textarea 加 placeholder「尚未填写拟证明事项，可在此补充」；
  - 有值时仍原样显示（AI 建议徽标 + 文本），不显示提示。
- 不涉及数据结构、材料包规则、导出规则。
- 浏览器复验（T4b）：空值→提示出现；编辑态 placeholder 出现；恢复值后原样显示且无提示。

### 8.3 修复后走查结果

重跑 `node walkthrough-9d3.mjs`：**PASS=44 / ISSUE=0 / MANUAL=2**（原 PASS=37/ISSUE=2/MANUAL=2）。
T5 四项全过（有确认、文案完整、取消不变、确认真合并）；T4b 三项全过。

---

## 9. 9-D-3b 补齐人工验证

### 9.1 导出 PDF 逐页视觉检查（不再只依赖文本抽取）

`walkthrough-9d3/t7-材料包卷宗.pdf`（3 页，A4），用 PyMuPDF 渲染每页为图片逐页查看：

| 页 | 检查项 | 结果 |
|---|---|---|
| 1 | 中文字体 | **正常**（STSong-Light CID 字体嵌入，无豆腐块/乱码） |
| 1 | 目录表格可读性 | **正常**（包内编号/材料名称/拟证明事项/原证据四列，边框清晰，内容完整） |
| 1 | 页脚 | **问题 P3**：「第 1 页 / 共 1 页」——总数错误，全文档 3 页却写「共 1 页」 |
| 2 | 材料1 原始内容可读性 | **正常**（劳动合同正文逐行可读，中英文混排无问题） |
| 2 | 页脚 | **问题 P3**：「第 2 页 / 共 2 页」 |
| 3 | 材料2 原始内容可读性 | **正常**（聊天记录时间戳+对话逐行可读） |
| 3 | 页脚 | **问题 P3**：「第 3 页 / 共 3 页」 |

- 根因（代码检查）：`services/export.py:77` `_page_footer` 用 `doc.page`（当前页码）当总页数。
  ReportLab 的 `doc.page` 在 build 期间就是「当前页」，真正总页数需要两遍 build 或
  `canvas` 保存。该问题**影响每一份 PDF 导出**，但不影响正文内容与可读性。
- 严重度：P3（正文/目录/字体/分页均正常，仅页脚总数错误；仲裁场景可能造成「缺页」疑虑）。
- 状态：**已记录，未修**（9-D-3a 只授权修走查发现的 P2/P3 两个问题；此问题为 9-D-3b 新发现，
  待用户决定是否修复）。

### 9.2 浏览器实测 409 VERSION_CONFLICT（此前标记「未验证」，现已验证）

- 触发方式：同一浏览器上下文开**两个标签页**同时打开同一材料包编辑页（draft_version 均为 1）；
  标签 A 勾选证据保存（1→2）；标签 B（页面仍持有旧值 1）勾选另一证据点「保存草稿」。
- API 实测响应：**409**，`{"error":{"code":"VERSION_CONFLICT","message":"材料包已被其他人修改，请重新加载后再次保存","request_id":"…"}}`
- 用户可见提示（截图 `walkthrough-9d3/15-t8-version-conflict.png`）：
  「材料包已被其他人修改，为避免覆盖你的修改，本次保存未生效。请重新加载最新草稿后再编辑。」+
  「重新加载」按钮。
- 数据一致性：冲突后服务端 `draft_version` 仍为 2（未被 B 的保存推进），B 的修改未落库。
- 此前 docs/17 §6 标记的「VERSION_CONFLICT UI 文案未在浏览器验证」现已闭环；
  `SNAPSHOT_REQUIRED` 仍由 Playwright 9-C 用例覆盖（本轮 12 passed 含该用例）。

---

## 10. 9-D-3a/3b 回归：命令与结果

| 命令 | 结果 |
|---|---|
| `cd backend && .venv/bin/pytest` | **271 passed**（新增 1 例 merge commit 回归），0 failed |
| `cd frontend && npm run lint` | exit 0（--max-warnings=0） |
| `cd frontend && npx tsc --noEmit` | exit 0 |
| `cd frontend && npx vitest run` | **23 passed**（新增 timeline-ui 1 例） |
| `cd frontend && npx playwright test` | **12 passed**（含 SNAPSHOT_REQUIRED 断言） |
| `bash scripts/e2e-smoke.sh` | 全流程通过（含时间轴步骤） |
| `bash scripts/e2e-material-packages.sh` | 14 步全部通过（含冲突防护、越权 404） |
| `bash scripts/e2e-real-materials.sh` | M1-M12 + 七跳链 + mock OCR 固化全部通过 |
| `alembic check` | No new upgrade operations |
| `node frontend/walkthrough-9d3.mjs` | **PASS=44 / ISSUE=0 / MANUAL=2** |

修改文件清单：
- `frontend/src/lib/timeline-ui.ts`（新增）
- `frontend/src/lib/timeline-ui.test.ts`（新增）
- `frontend/src/app/cases/[id]/timeline/page.tsx`（合并确认）
- `frontend/src/app/cases/[id]/evidence/page.tsx`（空值提示 + placeholder）
- `backend/app/routes/timeline.py`（merge 端点补 commit）
- `backend/tests/test_timeline.py`（新增 merge commit 回归测试）
- `frontend/walkthrough-9d3.mjs`（T4b/T5 验证增强）

## 11. 剩余问题（待用户决定）

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| 1 | PDF 页脚「共 N 页」总数错误（`export.py:77` 用当前页码当总页数） | P3 | 未修，已定位根因 |
| 2 | 卷宗排版观感（字体/分页/表格）已人工看图确认正常（§9.1），无需再人工 | — | 已闭环 |

**9-D-3a/3b 完成，等待确认后进入 9-D-4。**

---

## 12. 9-D-3c 修复：PDF 页脚总页数错误（P3）

授权：用户 2026-10-13 指令「先处理 9-D-3b 发现的 P3 页脚总页数错误问题」。

### 12.1 根因与修复

- 根因：`services/export.py` 的 `_page_footer(canvas, doc)` 用 `doc.page` 当总页数。
  ReportLab `SimpleDocTemplate.build()` 期间 `doc.page` 是**当前**页码（每页递增），
  因此 3 页文档每页分别显示「共 1 页」「共 2 页」「共 3 页」。
- 修复（不改导出内容结构、不换框架）：
  - `_page_footer` 改为接受 `total_pages` 的工厂，footer 写死真实总数；
  - 新增 `_build_pdf(story_factory)` 两遍构建：第一遍渲到临时 buffer 数页数
    （`probe.page` = build 结束后的总页数），第二遍用该总数出正式 PDF。
    footer 画在底部页边距内、不占 flowable 空间，两遍分页完全一致；
  - `render_pdf` 与 `render_package_pdf` 改为把 story 构造包成 `story_factory`
    传给 `_build_pdf`（ReportLab flowable 有状态，不能复用同一 story 建两次）。
- DOCX 无页码 footer（只有免责声明），不受影响。

### 12.2 测试

- 新增 `tests/test_package_export.py::test_pdf_footer_shows_true_total_page_count`：
  2 条材料的材料包导出 → 断言恰好 3 页，且
  - 每页都含「共 3 页」，
  - 第 1 页含「第 1 页 / 共 3 页」，第 2 页「第 2 页 / 共 3 页」，第 3 页「第 3 页 / 共 3 页」。
- 强化 `tests/test_export.py::test_export_pdf_contains_page_numbers`（案件导出）：
  逐页断言 `第 {i} 页 / 共 {total} 页`（total 取自 `pdf.page_count`）。
- 人工看图复核：新渲 3 页 PDF，第 1 页页脚显示「第 1 页 / 共 3 页」（文字层+渲染层双确认）。

### 12.3 回归（用户指定清单，全部实跑）

| 命令 | 结果 |
|---|---|
| `cd backend && .venv/bin/pytest` | **272 passed**（271 + 新增页脚 1 例），0 failed |
| `cd frontend && npx tsc --noEmit` | exit 0 |
| `cd frontend && npm run lint` | exit 0（--max-warnings=0） |
| `cd frontend && npx vitest run` | **23 passed** |
| `cd frontend && npx playwright test` | **12 passed** |
| `bash scripts/e2e-smoke.sh` | 全流程通过（含导出下载） |
| `bash scripts/e2e-material-packages.sh` | 14 步全部通过（含快照/冲突/越权） |
| `cd backend && .venv/bin/alembic check` | No new upgrade operations |

修改文件：`backend/app/services/export.py`（`_page_footer` + `_build_pdf` + 两个 render 函数）、
`backend/tests/test_package_export.py`（新增用例）、`backend/tests/test_export.py`（强化断言）。

**9-D-3c 完成，进入 9-D-4（部署风险处置，已获批准）。**

---

## 13. 9-D-4 部署风险处置（2026-10-14）

范围（经用户批准）：R1 补 `backend/Dockerfile`、`frontend/Dockerfile` + compose 静态评审；
R4 新增 `scripts/backup.sh`/`scripts/restore.sh` 并本机真实演练一轮。R3/R6 等其余风险不改。

### 13.1 R1 — Dockerfile 补写 + compose 静态评审

**新增文件**

- `backend/Dockerfile`：`python:3.11-slim` 基底；`libmagic1`（python-magic）+ `curl`（HEALTHCHECK）；
  pip 安装 `requirements.txt`；非 root `appuser`；启动时 `alembic upgrade head && uvicorn`；
  `HEALTHCHECK` 打 `/healthz`。
- `backend/.dockerignore`：排除 `.venv`/`var/`/`tests/`/`.env` 等（不把密钥和上传数据烤进镜像）。
- `frontend/Dockerfile`：`node:20-alpine` 多阶段（`npm ci` → `next build` → `next start`）；
  **`NEXT_PUBLIC_API_BASE_URL` 作为 build arg**（Next 客户端 bundle 在构建期内联该变量，
  仅设 runtime env 无效）；`USER node`；`EXPOSE 3000`。
- `frontend/.dockerignore`：排除 `node_modules`/`.next`/`test-results`/`e2e` 等。

**compose 静态评审结论**（`docker compose config` 无法实跑，仅人工核对 + `yaml.safe_load`）

| 检查项 | 结论 |
|---|---|
| 引用文件存在 | ✅ `./backend`、`./frontend` 两个 build context 现均有 `Dockerfile` |
| `NEXT_PUBLIC_API_BASE_URL` 传递方式 | ⚠️ 原 compose 只在 frontend `environment` 设置——**构建期内联变量这样做无效**；已在 compose 为 frontend 增加 `build.args.NEXT_PUBLIC_API_BASE_URL`，保留原 environment（对非 NEXT_PUBLIC 变量仍有意义，此处仅为兼容阅读者直觉） |
| backend 服务命令/端口/依赖 | ✅ 与 Dockerfile 的 8000 端口、healthz 路径一致 |
| worker 服务（rq） | ❌ **R6 确认**：命令 `rq worker --url …` 但 `rq`/`redis` 不在 `backend/requirements.txt`，`grep import redis\|import rq\|from rq\|from redis backend/app` 零命中——按现状该容器必失败启动。属批准范围外（需补依赖+实现 enqueue 路径），**未修，仅登记** |
| SECRET_KEY / 数据库口令 | ⚠️ R3（硬编码 `leo_dev_pw`、回退 `change-me-in-production`）**未修**，属范围外 |
| 卷权限（R12） | 无法验证（无 docker） |

**静态评审发现但未修改的其他项**：compose 无 HTTPS/反代（R10）；限流进程内（R9）——均记录于风险登记册。

### 13.2 R4 — 备份/恢复脚本

**新增文件**

- `scripts/backup.sh`：`pg_dump --format=custom --no-owner --no-privileges` → `db.dump`；
  `tar -czf storage.tar.gz` 整个 `STORAGE_ROOT`；写 `manifest.txt`（时间戳、URL、
  bytes、`cases`/`evidence` 行数）。默认 `DATABASE_URL`/`STORAGE_ROOT` 与 `app/config.py`
  一致，可用环境变量覆盖。
- `scripts/restore.sh`：`pg_restore --clean --if-exists --no-owner --no-privileges`；
  删除旧 storage 后解包 tar；**恢复后自动 `psql` 核对 cases/evidence 行数与 manifest
  一致**，不一致则非零退出。

### 13.3 本机真实演练（marker 注入→备份→删除→恢复→核对）

真实 PostgreSQL 15 + 真实 storage（1.7G / 72 案件 / 91 份证据）：

1. **注入 marker**：插入案件 `9d4-drill-marker-case`（UUID `9d400000-…-0001`）+ storage
   目录 `cases/<id>/marker.txt`。
2. **备份**：`scripts/backup.sh /tmp/leo-backup-drill` →
   `db.dump` 168K、`storage.tar.gz` 909M、`cases_count: 73`、`evidence_count: 91`。
3. **删除**：`DELETE FROM cases` + `rm -rf` storage 目录——marker 双侧消失，确认丢失。
4. **恢复**：`scripts/restore.sh /tmp/leo-backup-drill` → pg_restore 干净恢复；
   自动核对 `cases 73 (expected 73), evidence 91 (expected 91)` 通过。
5. **逐字段验证**：案件 `name=9d4-drill-marker-case` 恢复；`marker.txt` 内容
   `marker-2026-10-14T02:17:56Z` 与删除前**逐字节一致**。
6. **清理**：删除 marker 行/目录及 /tmp 演练备份；`cases` 回到基线 72。

演练结论：**脚本可用，恢复字节级一致；试用真实材料前必须先跑一次 backup.sh**。

### 13.4 9-D-4 遗留（不属本阶段，登记不修）

- R3：SECRET_KEY/库口令硬编码——生产部署前必须处理（待批）。
- R6：compose rq worker 缺 `rq`/`redis` 依赖——容器部署前必须补（待批）。
- R10/R12：HTTPS 反代、容器卷权限——需有 Docker 的环境验证。

**9-D-4 完成，进入 9-D-5（汇总报告）。**
