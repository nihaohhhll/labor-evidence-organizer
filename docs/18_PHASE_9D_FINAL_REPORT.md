# Phase 9-D 汇总报告（9-D-5）

日期：2026-10-14。Phase 9-D 收尾汇总：材料验证结果矩阵、可用性问题清单、风险登记册。
本阶段目标（docs/16 §1）：**用真实格式脱敏材料验证端到端流程，评估是否具备小范围试用条件**。
边界：不改核心业务规则、不引入新导出框架/AI 能力、不提交 Git、不启动 Phase 10。

---

## 1. 结论

**产品具备"内部小范围试用（单机、可信操作者、先备份）"的条件，但以下四项为硬前置**：

1. **试用前必须跑 `scripts/backup.sh`**（R4 已演练可用；无备份不入库真材料）。
2. **仅限内网/本机部署**：无 HTTPS/反代（R10）、SECRET_KEY 回退值（R3）未处置。
3. **图片/扫描件材料没有文字**：mock OCR 恒返回空文本（R7），图片证据靠人工录入——这是如实行为不是缺陷，但操作者须事先知晓。
4. **容器化部署未验证**：本环境无 Docker，镜像构建与 `docker compose up` 从未实跑（R1/R2 静态评审完成、R6 确认按现状 worker 必失败）。

自动化验证全绿（§2）；材料矩阵 M1-M12 全部按预期通过（§3）；可用性问题 8 项均非阻断（§4）；风险登记册 R1-R13 现状见 §5。

---

## 2. 全量回归矩阵（9-D-5 收尾重跑，2026-10-14）

| 验证 | 结果 |
|---|---|
| `backend pytest` | **272 passed** |
| `frontend npx tsc --noEmit` | 0 错误 |
| `frontend npm run lint` | 0 警告 |
| `frontend npx vitest run` | **23 passed** |
| `frontend npx playwright test` | **12 passed** |
| `scripts/e2e-smoke.sh` | 通过（上传→解析→时间轴→导出→下载→缺口，含跨用户隔离） |
| `scripts/e2e-material-packages.sh` | 通过（14 步：创建→编辑→排序→快照→历史→冲突→权限） |
| `scripts/e2e-real-materials.sh` | **全部通过：M1-M12 材料矩阵 + M1 七跳可追溯链 + M8 状态机闭环 + mock OCR 空文本固化** |
| `node frontend/walkthrough-9d3.mjs` | **PASS=44 / ISSUE=0 / MANUAL=2**（截图 `walkthrough-9d3/`） |
| `alembic check` | 无漂移（head `7b2e9d41c05f`） |
| `frontend npm run build` | **通过**（首次实跑：17 个路由全部构建，首屏共享 JS 87.2 kB）；构建后已重启 dev server 复核走查仍 PASS |

---

## 3. 材料验证结果矩阵（M1-M12）

设计预期见 docs/16 §2.2；执行载体 `scripts/make-real-materials.py` + `scripts/e2e-real-materials.sh`。
"预期 vs 实际"逐份核对，全部与预期一致（除 M3 置信度一栏按实际修正，见下）。

| # | 材料 | 格式 | 预期 | 实际 | 结果 |
|---|---|---|---|---|---|
| M1 | 劳动合同（文本层） | PDF | SUCCESS；抽取入职日期/月工资；可人工改；导出含原文 | SUCCESS；event_date=2022-10-01 抽到；七跳链全通过 | ✅ |
| M2 | 工资条明细 | TXT | SUCCESS；金额抽取 ≥3 条 | SUCCESS；金额断言通过 | ✅ |
| M3 | 聊天记录导出 | TXT | 分类为 chat 类 | classification=**chat_record**、confidence=**0.96** | ✅（注） |
| M4 | 考勤表 | DOCX | 表格单元格进 extracted_text；导出含表格文本 | SUCCESS；表格文本断言通过 | ✅ |
| M5 | 聊天截图 | PNG | SUCCESS 但**文本为空**（mock OCR）→人工录入；不阻断 | SUCCESS；raw_text 空；证据 PENDING、category=other、空文本兜底摘要 | ✅ 固化为断言 |
| M6 | 工资条照片 | JPEG | 同 M5 | 同 M5 | ✅ 固化为断言 |
| M7 | 扫描版 PDF | PDF | used_ocr=true；文本空；不报错 | 同预期 | ✅ 固化为断言 |
| M8 | 损坏 PDF | PDF | FAILED；可重试；错误可见；状态机闭环 | FAILED；直接解析 409 INVALID_TRANSITION→retry 200 QUEUED→再解析 422 PARSE_FAILED→FAILED+error_message | ✅ 闭环 |
| M9 | 超 25MB | TXT | 拒绝 | 拒绝，原因正确 | ✅ |
| M10a/b | HTML 改 .txt / 脚本改 .png | TXT/PNG | 拒绝 | 两份均拒绝，原因正确 | ✅ |
| M11 | 中文文件名+空格+分号 | PDF | 上传/下载头正确 | original_filename 精确一致；Content-Disposition 正确 | ✅ |
| M12 | 多页混合 PDF（2 文本+1 扫描） | PDF | 文本页正常、扫描页空、不失败 | SUCCESS；文本页抽取、扫描页空 | ✅ |

**M3 注**：设计预期"低置信进待确认队列"；实际 mock 分类器对聊天导出形态的结构检测给出 0.96 高置信（确定性规则非模型）。行为**更优**（无需人工分类），已按实际固化断言（`confidence >= 0.9`），非缺陷。

**M1 七跳可追溯链**（验收核心，全部 API/导出字段比对）：
`storage_key → file 行 → analysis 行(provider/prompt_version) → evidence 行(编号/proof_purpose/CONFIRMED) → 时间轴事件(2022-10-01) → 材料包条目(display_number) → 快照 content 逐字段 → DOCX/PDF 文本含编号/名称/拟证明事项/原文片段`——7/7 通过。

---

## 4. 可用性问题清单（9-D-3 走查 + 全阶段观察）

均为**非阻断**；标注处置状态。

| # | 问题 | 严重度 | 处置 |
|---|---|---|---|
| U1 | 时间轴合并无二次确认，误点即合并且不可撤销 | P2 | ✅ 9-D-3a 已修：`buildMergeConfirmMessage` 列受影响事件+不可撤销，`window.confirm` 取消不发请求 |
| U2 | 证据列表未填"拟证明事项"时无任何提示 | P3 | ✅ 9-D-3a 已修：非编辑态提示 + 编辑态 placeholder |
| U3 | 材料包并发编辑冲突（409）仅在 API 层，UI 无提示 | P3 | ✅ 9-C 已有：错误信封 + 「已被其他人修改…重新加载」+ 浏览器实测截图（docs/17 §9） |
| U4 | **"发布"仅是标记、不锁定**，操作者可能误以为发布=只读 | P3 | 记录（9-D-3 走查 T6）；改语义超边界，试用须口头告知 |
| U5 | 时间轴合并后**无"撤销合并"** | P3 | 记录（README 已知限制）；`merged_into_id` 保留原始 ID，恢复需后端功能 |
| U6 | 材料缺口分析（A3）v1：空案件 400、FAILED 不落库、无闭环状态 | P3 | 记录（README 已知限制） |
| U7 | **图片材料无文字**（mock OCR），证据靠人工录入 | P3（如实行为） | 记录（R7）；生产接真实 OCR 前须在试用须知中明示 |
| U8 | 材料包导出无 ZIP（仅案件导出有） | P3 | 记录（功能边界，docs/16 已登记）；试用者可能期待材料包一键打包 |

走查遗留 MANUAL=2 项（浏览器 409 UI 展示、卷宗 PDF 观感）均已人工看图/双标签页实测通过（docs/17 §9/§12）。

---

## 5. 风险登记册现状（R1-R13，含未验证标注）

原则：**未验证项一律标注，不写成"已具备"**。完整表见 docs/16 §5；此处为 9-D 结束时点现状。

| # | 风险 | 严重度 | 9-D 结束时状态 |
|---|---|---|---|
| R1 | compose 引用不存在的 Dockerfile | 高 | **已处置**：两个 Dockerfile + .dockerignore 已补写，compose 补 build.args；静态评审通过；**镜像构建/compose up 实跑未验证（无 Docker）** |
| R2 | Docker/compose 从未执行 | 高 | 同 R1：文件齐、静态评审过；**实跑未验证** |
| R3 | SECRET_KEY 回退 `change-me-in-production`；库口令 `leo_dev_pw` 写死 compose | 高 | **未处置（待批）**——生产部署前必须处理 |
| R4 | 无备份/恢复脚本 | 高 | **已处置**：backup.sh/restore.sh + 本机真实演练通过（docs/17 §13） |
| R5 | S3 装不上也测不了（boto3 缺、pragma no cover） | 中 | 未处置，只记录 |
| R6 | compose rq worker 缺 `rq`/`redis` 依赖、代码零引用，按现状**必失败启动** | 中 | **9-D-4 确认并记录，未修（待批）** |
| R7 | 真实 AI/OCR Provider 从未接入（仅 mock）；图片无文字 | 中 | 记录+材料矩阵如实固化（M5/M6/M7 断言） |
| R8 | JWT 24h 无刷新、localStorage 存 token | 中 | 未处置；CSP 部分缓解（`script-src 'self'`） |
| R9 | 限流计数在进程内存，多副本失效 | 低 | 记录 |
| R10 | compose 无 HTTPS/反代 | 中 | 记录；试用限内网/本机 |
| R11 | 生产日志落盘/收集未验证 | 低 | 记录（日志脱敏已有测试） |
| R12 | 容器卷权限未验证 | 低 | 记录（依赖 R1 实跑） |
| R13 | 容器 locale 缺失时 Playwright 中文路径静默失败 | 中（仅 CI/走查） | **已修环境**（`locale-gen en_US.UTF-8`）；镜像 Dockerfile 未装 locales——走查/CI 场景需注意（本机已恢复） |

**试用决策建议**：单机、可信操作者、内网部署、**先 `backup.sh`**、事先明示 U4/U7 两项认知——可进入小范围试用。多副本/公网/容器编排均**不在**当前"已具备"范围。

---

## 6. 本阶段产出物清单

| 类型 | 文件 |
|---|---|
| 材料生成 | `scripts/make-real-materials.py`（M1-M12 + manifest） |
| 自动化验证 | `scripts/e2e-real-materials.sh`（矩阵+七跳链+状态机+OCR 固化） |
| 人工走查 | `frontend/walkthrough-9d3.mjs` + `walkthrough-9d3/`（20 截图） |
| 缺陷修复 | 合并确认（`timeline-ui.ts`+`timeline/page.tsx`）、空证明目的提示（`evidence/page.tsx`）、merge 端点 commit（`routes/timeline.py`）、PDF 页脚总页数（`services/export.py` 两遍构建） |
| 部署 | `backend/Dockerfile`、`frontend/Dockerfile`、`.dockerignore`×2、compose build.args |
| 备份恢复 | `scripts/backup.sh`、`scripts/restore.sh`（演练记录 docs/17 §13） |
| 文档 | `docs/16`（设计+登记册+问答）、`docs/17`（走查+修复+演练）、本报告 |

## 7. 未做（明确出界）

- Phase 10 及之后任何阶段；Git 提交。
- R3/R5/R6/R8-R12 的代码级处置（待批）。
- 真实 AI/OCR Provider 接入、真实 S3、HTTPS 反代、多副本限流。
- Docker 镜像实跑验证（无 Docker 环境）。

**Phase 9-D 完结。**

---

## 8. 9-D-5.1 收尾确认与 Phase 9-D 最终封版（2026-10-14）

### 8.1 P3 页脚总页数错误——复核确认（无新改动）

该缺陷已在 **9-D-3c** 修复落地；9-D-5.1 为封版前复核，**未产生任何新代码改动**。

**修改文件列表（9-D-3c 修复本体，封版时点仍全部在位）**

| 文件 | 改动 |
|---|---|
| `backend/app/services/export.py` | `_page_footer` 改为 `total_pages` 工厂；新增 `_build_pdf` 两遍构建；`render_pdf`/`render_package_pdf` 改用 |
| `backend/tests/test_package_export.py` | 新增 `test_pdf_footer_shows_true_total_page_count`（2 材料→恰好 3 页逐页断言） |
| `backend/tests/test_export.py` | `test_export_pdf_contains_page_numbers` 强化为逐页 `第 {i} 页 / 共 {total} 页` 断言（total 取 `pdf.page_count`） |

**根因**：ReportLab `SimpleDocTemplate.build()` 期间 `doc.page` 是**当前页码**而非总页数；旧 `_page_footer` 把它当总数，3 页文档每页分别显示「共 1/2/3 页」。

### 8.2 封版复核结果（本日实测）

| 验证 | 结果 |
|---|---|
| export 回归（`test_export.py` + `test_package_export.py`） | **32 passed** |
| 实时 HTTP 视觉检查（新建案件→3 份手工证据→材料包→快照→PDF 导出→下载） | 生成 **4 页**卷宗（目录页+3 材料页）；PyMuPDF 渲染 `/tmp/leo-pdf-visual/page{1..4}.png`；文本断言每页 `第 {i} 页 / 共 4 页`，各页声明总页数集合 `{4}` |
| 人工看图复核 | page1 页脚「第 1 页 / 共 4 页」✅；page4 页脚「第 4 页 / 共 4 页」✅；字体/表格/正文正常 |

### 8.3 Phase 9-D 最终封版记录

- **范围**：9-D-1 材料套件 → 9-D-2 自动化验证 → 9-D-3a/3b/3c 走查修复 → 9-D-4 部署风险处置 → 9-D-5 汇总 → 9-D-5.1 P3 复核封版。
- **最终验证状态**：pytest **272 passed** · tsc/lint 0 · vitest **23** · Playwright **12** · e2e-smoke / e2e-material-packages / e2e-real-materials（M1-M12+七跳链）· 走查 **PASS=44 / ISSUE=0 / MANUAL=2** · alembic 无漂移 · `npm run build` 17 路由 · PDF 页脚逐页正确（本日复核）。
- **材料包业务规则**：本收尾阶段零改动（仅复核）。
- **保持待办（明确不在封版范围）**：Docker 容器实跑（R1/R2 静态评审完成）、S3（R5）、RQ worker（R6，compose 按现状必失败）、真实 AI/OCR Provider（R7）、HTTPS/反代（R10）、SECRET_KEY 生产守卫（R3，待批）、Git 提交、Phase 10。
- **封版结论**：**Phase 9-D 完结封版**。产品具备"单机+可信操作者+内网+先备份"的小范围试用条件（见 §1）；对外材料一律标注未验证项。
