# Changelog

本项目遵循 `docs/13_DEVELOPMENT_PLAN.md` 的 Phase 划分。所有条目均为**已实现并有测试覆盖**的功能。

## Unreleased

### Phase 0 — 规格与骨架
- 导入 18 份规格文档到 `docs/`，附工程复盘 `labor_evidence_organizer_project_engineering_log.md`。
- 仓库初始化、`.gitignore`、`.env.example`、`docker-compose.yml`（db / backend / worker / redis / frontend）。

### Phase 1 — 基础设施
- FastAPI 应用骨架：统一错误信封、`X-Request-ID` 中间件、lifespan 日志。
- PostgreSQL 15 + Alembic：14 张表，`alembic check` 无漂移。
- 用户认证：注册 / 登录 / `me`，bcrypt 哈希 + JWT。
- Case CRUD：软删除、分页、跨用户隔离（404 而非 403，避免泄露资源存在性）。
- Next.js 前端：登录注册、案件列表（loading/empty/error 三态）、案件创建、案件 Dashboard。

### Phase 2 — 文件管理
- 批量上传，单个文件失败不影响整批（返回 `skipped` 及原因）。
- SHA-256 按案件去重；同内容跨案件各自保留。
- 双重校验：扩展名白名单 + magic bytes 签名，改名攻击被拒绝。
- `LocalStorage` 写入后拒绝覆盖不同内容，保证原始证据不可变；键值防路径穿越。
- 文件状态机 `UPLOADED → QUEUED → PROCESSING → REVIEW_REQUIRED/COMPLETED/FAILED`，软删除，失败重试。
- 鉴权下载原始文件，`nosniff` + `no-store` 响应头。

### Phase 3 — 解析与 AI
- PDF（文本层优先，无文本层转 OCR）、DOCX（段落 + 表格）、TXT、图片解析。
- `AIProvider` / `OCRProvider` 协议抽象，业务代码不接触厂商 SDK；provider 注册表按配置名解析。
- 确定性规则抽取：日期（中英文格式、触发词前后双向匹配）、金额（保留原始单位与货币符号）、人物、组织。
- 分类改为**全规则打分**，避免 `劳动合同` 子串吞掉 `解除劳动合同通知书`。
- 分析结果持久化 `provider / model / prompt_version / confidence`，重新分析追加新行而非改写。
- 低于 0.80 置信度强制进入人工确认队列。

### Phase 4 — 证据管理
- Evidence / Event / Person 及三张关联表，证据编号按案件自动分配并有唯一约束兜底。
- 人工新增证据同样由服务端分配编号。
- 分类、日期、摘要、证明目的均可编辑。

### Phase 5 — 人工审核
- 审核工作台：左侧原始材料、右侧 AI 结果与人工版本并列。
- `review_items` 队列，支持保存用户值、确认、忽略。
- **版本保护**：`evidence.user_edited_fields` 记录人工改过的字段；`reanalyze` 跳过这些字段，未改字段照常刷新。

### Phase 6 — 时间轴
- 从已确认证据推导事件，按 (日期, 标题) 分组去重，**重复构建幂等**。
- 事件编辑（含 `precision` 结构化字段，避免依赖展示文案判断状态）、删除、多选合并。
- 合并保留全部证据关联，被合并事件记录 `merged_into_id`。

### Phase 7 — 导出
- DOCX（证据目录 + 时间轴）、PDF（`第 X 页 / 共 Y 页` 页码）、ZIP（文档 + CSV 索引 + 原始文件）。
- 编号 `证据1、证据2…`，排序严格按 `evidence_number`。
- 只导出已确认数据；无可导出内容时返回 `409 NOTHING_TO_EXPORT`。
- 案件名清洗路径分隔符；中文文件名经 RFC 5987 编码。

### 工程
- 105 个后端测试（单元 + 集成），`scripts/e2e-smoke.sh` 端到端验收脚本覆盖完整闭环。
- 前端 `tsc --noEmit`、`eslint --max-warnings=0`、`npm run build` 全部通过。

### Phase 9-A — 仲裁材料包生成器（基础层）
- 数据模型：`material_packages`（草稿 + `draft_version` 乐观锁）、`material_package_items`（顺序/编号唯一约束，DEFERRABLE 以支持原子重排）、`material_package_snapshots`（不可变快照，完整序列化内容）。
- 服务层：跨案件证据引用拒绝（与不存在的 ID 返回同一错误码，防探测）、顺序/编号按 payload 位置分配、并发保存版本冲突 409、快照防重复提交、快照读取时标注来源证据 `OK/CHANGED/MISSING`。
- API：`/cases/{id}/material-packages`（创建/列表）、`/material-packages/{id}`（详情/改名/状态/删除）、`/items`（GET/PUT 批量保存）、`/snapshots`（创建/历史/指定版本读取）；可选证据列表复用现有 `/cases/{id}/evidence`。
- 约束：不修改 Evidence/File/Event/Timeline 核心模型与 A1/A2/A3；无 LLM；无导出。
- 测试：新增 28 个用例（共 205 个后端测试全部通过），`alembic check` 无漂移，迁移 up/down 往返验证通过。

### Phase 9-B — 材料包编排与审核页面
- 前端页面：材料包列表（含空状态引导）、新建草稿、三区域编辑页（可选证据筛选/勾选、条目顺序与展示名称/拟证明事项/审核状态编辑、原始证据预览）、历史快照列表、快照只读详情；案件详情页新增材料包入口。
- 交互：脏标记与未保存提示（浏览器关闭/刷新 + 站内导航双重拦截）、保存/快照的 loading/成功/失败态、版本冲突 409 显式提示并提供重新加载（不静默覆盖）、来源文件缺失 410 显式报错（不以 OCR 文本替代原件）。
- 鉴权预览：`api.fetchFileContent` 带 token 获取 blob URL，`<img>`/`<iframe>` 预览保留后端权限校验；快照页按 `source_status` 显式标注来源异常。
- 纯逻辑抽取到 `lib/material-package-ui.ts`（增删/排序/编号/payload 序列化），vitest 单测覆盖。
- 新增 `scripts/e2e-material-packages.sh`：14 步真实 HTTP 端到端（创建/添加/移除/排序/持久化/审核状态/快照只读/冲突 409/跨案件 404/越权 404/快照只读通道/来源 MISSING/前端路由探活）。
- 测试：后端 205 个全部通过（零回归），前端 `vitest` 8/8、`tsc --noEmit`、`eslint --max-warnings=0`、`next build` 全部通过，`e2e-smoke.sh`（上传→解析→核对→时间轴→导出全流程）通过。
- 收尾修复（第二轮）：`scripts/e2e-material-packages.sh` 第 13 步硬编码根目录 `.venv`（实际 venv 在 `backend/.venv`），导致该步在本机**永远静默跳过**；改用脚本已有的 `$PY` 变量。修复后在前后端同时运行的环境下 **14/14 步全部真实执行**（含 `source_status=MISSING` 来源异常标注与 5 个前端路由探活，无任何跳过）；回归验证后端 235 / 前端 17 全绿。

### Phase 8-A3 — 材料缺口分析（测试与前端补齐）
- 后端修复（`app/services/evidence_gaps.py`）：
  - 修复 Rule-1 触发即崩溃的 bug（`uuid.UUID("…:标签")` 复合 ID 无法解析）；事实 ID 改为确定性 `uuid5(case_id, 标签)`。
  - 期望/建议类型改回系统 EvidenceType 封闭词表：`salary_record`/`bank_record` → `salary_statement`/`bank_statement`；Rule-5 建议类型 `["any"]` → `chat_record/attendance_record/work_record`。
  - 支持检查改为**全案件范围**（案件内存在任一期望类型证据即视为有支持），消除"合同在案仍报缺口"的误报。
  - 补齐四道 service 层闸门顺序：中性 → 无义务措辞 → 来源可追溯（`sources` 不再恒为空）→ `GapJson` schema；摘录是用户材料原文引用，不过措辞闸门。
  - `gap_id` 由随机 uuid4 改为确定性 uuid5，实现设计要求的跨版本指纹。
  - `gap_json` 内 UUID 统一序列化为字符串（修复 JSON 持久化 TypeError）。
- Migration 修复：`443a6f78858c` 与 `45c25bf47d58` 重复创建/删除同一索引，全新库 `upgrade head` 与 `downgrade base` 必然失败；已对称修复，`upgrade → downgrade → upgrade` 往返通过、`alembic check` 无漂移。
- 测试：新增 `tests/test_evidence_gaps.py` **30 例**（API 契约/越权 404/版本不可变/history 分页/两条规则触发与抑制/决策 2&4 不出现/闸门变异测试/词表断言/mock 流水线集成）。
- 前端：`evidence-gaps` 页面补**历史版本列表**（查看/回到最新）、缺口条目展示**来源摘录与搜索依据**；新增纯逻辑 `lib/evidence-gap-ui.ts` + vitest 9 例。
- e2e：`e2e-smoke.sh` 新增「材料缺口分析（A3）」步骤（结构契约 + Rule-1 专项案件 + 缺口端点越权 404），全流程通过。
- 依赖：`requirements.txt` 补充 `python-magic`（缺失时全部 `.txt` 上传被"内容与扩展名不一致"拒绝，曾导致 48 个既有测试连锁失败）。
- 文档：`docs/06`（A3 三端点与规则）、`docs/12`（A3 测试计划与 Scenario 6）、`docs/13`（Phase 8-A3）已更新。
- 未做（按设计决策）：闭环状态、`EVENT_NO_EVIDENCE`、`FACT_SINGLE_SOURCE`、空案件 409、`FAILED` 状态落库（DB 故障时仍为 500，无兜底行）。

### Phase 9-C — 仲裁材料包成卷导出（PDF/DOCX）与状态机放开
- 状态机（决策 2）：发布 = 纯状态标记，发布后仍可编辑；仅 `ARCHIVED` 只读，编辑 → 409 `NOT_EDITABLE`；有快照的草稿不可删除 → 409 `HAS_SNAPSHOTS`（删除限制从一律 `NOT_DRAFT` 收紧而来）；空包不能创建快照 → 409 `EMPTY_PACKAGE`。
- 成卷导出（决策 4）：新增 `POST/GET /material-packages/{id}/exports`，仅 PDF/DOCX（不产 ZIP）。按快照渲染（未传 `snapshot_version` 取最新；无任何快照 → 409 `SNAPSHOT_REQUIRED`），导出记录绑定 `package_id/snapshot_id/snapshot_version/include_gap_appendix/gap_result_id` 并写审计 `EXPORT_CREATED`；非法格式 → 422 `UNSUPPORTED_FORMAT`。
- 内容组装：逐条嵌入原始内容，按 item 隔离异常（单条失败不阻断整卷）；已删文件 → 「原始文件已删除」注记、无文件有摘要 → 手工录入文本、来源证据已删 → 注记；无法转换的原件显式标注；扫描图片栅格化 cap 30 页/文件 + 显式截断注记；PDF 纯文字回退、图片按原始纵横比缩放（≤170×200mm）、每材料分页、CJK 换行。
- 完整性附录（决策 1）：中性「材料完整性提示」开关（无 A1/A2，正文与附录均不输出 `review_status`）；无 A3 成功结果 → 409 `GAP_APPENDIX_UNAVAILABLE`；草稿晚于分析时标注 stale 提醒。
- 下载：`GET /exports/{id}/download` 对包导出输出 `材料包-{名称}.{pdf|docx}`（RFC 5987 编码，ASCII 回退）。
- 前端（决策 5/6）：新建导出成卷页（格式/快照选择/附录开关与禁用提示/生成/记录列表/带鉴权 blob 下载）；编辑页仅 ARCHIVED 只读 + 发布/归档按钮 + 快照分歧提醒；列表页 `limit=100` 拉取 + 超限提示（修复 20 条静默截断）+ 发布/删除（`DRAFT && snapshot_count==0` + confirm）；案件导出中心 401 裸链接改带鉴权 blob 下载。
- 修复：材料包编辑页 StrictMode 双重加载竞态——晚到的旧响应会清空用户刚勾选的条目；`loadSeq` 序号丢弃过期成功/失败响应。
- CORS（缺口补录）：此前后端未注册任何 CORSMiddleware（OPTIONS 预检 → 405，浏览器跨源全挂；既有 e2e 均为 curl 同源故未暴露）。现于最外层注册，`cors_allow_origins` 白名单（默认 `localhost:3000`/`127.0.0.1:3000`，见 `.env.example`），`allow_credentials=false`，暴露 `Content-Disposition`/`X-Request-ID`；决策记录见 `docs/11` 第 14 条。
- Playwright UI E2E（决策 6）：`frontend/playwright.config.ts` + `e2e/helpers.ts` + `e2e/phase9c-ui.spec.ts` 共 11 个场景，入口 `scripts/e2e-ui.sh`。限流（register 5/60s、login 10/60s）下全程共享 1 个账号并经 `addInitScript` 注入 token。踩坑记录：request context 绝对路径会丢 `/api/v1` 前缀（baseURL 尾斜杠 + 全部相对路径）、`download.failure()` 是 Promise 必须 await、React 受控 checkbox 用 `click()` + 轮询断言（`check()` 即时校验会与受控重渲染竞态）。
- 脚本修复：`dev-restart-backend.sh` venv 路径（根 `.venv` 不存在，实为 `backend/.venv`）、`e2e-smoke.sh`/`e2e-material-packages.sh` 的 `$PY` 默认值同步修正。
- 文档：`docs/06`（Material Packages 全端点与错误码、导出下载文件名、CORS 规则）、`docs/11`（CORS 决策）、`docs/12`（9-C 单元/集成清单 + Scenario 7 的 11 场景）、`docs/13`（Phase 9-A/9-B/9-C 完成状态）、README（验证状态与端点数）已同步。
- 测试：后端 **250 passed**（+15：`tests/test_package_export.py` 14 例 + 材料包状态机 1 例），前端 vitest 17、`tsc --noEmit`、`eslint`（src+e2e）、`next build`（17 路由）全绿；`scripts/e2e-ui.sh` Playwright **11/11 连续两轮**、`e2e-smoke.sh` 通过、`e2e-material-packages.sh` 14/14、`alembic check` 无漂移。
- 未做（按 9-C 边界）：9-D/10 阶段内容、ZIP 打包、A1/A2 附录、Git 提交。

### Phase 9-C 收尾验收 — 下载文件名兼容与验收加固
- 缺陷修复（下载文件名 ASCII 回退）：`content_disposition` 原实现对中文名做 `encode("ascii","ignore")` 后得到 `-.pdf` 这类空壳回退，且不清理 `"`/`;`/`/`/`\` 与控制字符。现改为 `_ascii_fallback`：仅保留可打印 ASCII、剥离 quoted-string 元字符、`/` 与 `;` 中性化为 `_`、去除路径穿越形态、扩展名前无可用词干时回退通用 `download`，保证回退**合理非空**且头值始终可 latin-1 编码；`filename*=UTF-8''`（RFC 5987）行为不变，仍是现代浏览器的精确名来源。
- 前端 `parseDownloadFilename` 导出为公开函数（供 vitest 覆盖）：`filename*` 优先、解码失败/空值落到 plain 参数、统一 trim；`downloadWithAuth` 逻辑不变。
- 修复前端单测入口：vitest 默认 include 会误收 `e2e/phase9c-ui.spec.ts`（Playwright spec）导致 `npm test` 失败，新增 `frontend/vitest.config.ts` 将 include 限定为 `src/**`。
- 新增测试：后端 `tests/test_http_headers.py` 13 例（中文/英文/空格/特殊字符/CRLF 注入/穿越/inline/头形状）；`test_package_export.py` +4（英文空格名与特殊字符名的下载头、未传 `snapshot_version` 绑定最新快照而非草稿、渲染失败留 FAILED 行 + `RENDER_FAILED`）；`test_export.py` +3（下载 404 `EXPORT_NOT_FOUND` / 409 `EXPORT_NOT_READY` / 410 `EXPORT_MISSING`）；PDF 成卷测试补 pymupdf 文本断言（含原始内容、不含 `review_status`/`CONFIRMED`）；前端 vitest +5（`parseDownloadFilename` 全分支）。
- Playwright 增至 **12 场景**：scenario 6 增加真实保存名断言；scenario 12 覆盖英文/空格/特殊字符包名（响应头回退断言 + 页面侧 `a.download` 赋值断言）。踩坑：headless Chromium 会丢弃**含非 ASCII 字符**的 `a.download` 值（裸锚点探测亦复现，`suggestedFilename()` 报默认 `download`），故中文名的浏览器侧保存名通过拦截 `HTMLAnchorElement.prototype.click` 断言赋值字符串，而非 `suggestedFilename()`。
- 回归：后端 **270 passed**（+20），前端 vitest 22、`tsc`、`eslint`（src+e2e）、`next build` 全绿；Playwright **12/12**、`e2e-material-packages.sh` 14/14、`e2e-smoke.sh` 通过、`alembic check` 无漂移。
- 未做（按验收边界）：9-D/10 阶段、ZIP 打包、A1/A2 附录、Docker/S3/真实 AI Provider 验证、Git 提交。

### Phase 9-D-1/9-D-2 — 真实脱敏材料端到端验证（已完成）
- 材料套件（9-D-1）：`scripts/make-real-materials.py` 运行时生成 13 份材料（M1-M12，含 M10a/b 两份伪装样本）：PDF 文本层/DOCX 表格/TXT/聊天形态/图片/扫描 PDF/损坏 PDF/超大文件/改名攻击/中文文件名+分号/多页混合 PDF；输出 manifest（sha256 + 逐份预期行为），二进制不入库；脱敏规则：虚构姓名/单位，证件号与卡号为故意无效演示值，不生成二维码。
- 自动化验证（9-D-2）：`scripts/e2e-real-materials.sh` 对运行中后端真实 HTTP 验证：M1-M12 逐份上传/解析/状态断言（含拒绝样本原因）；**M1 七跳可追溯链**（file sha256 三处一致 → analysis 结构化字段 → evidence PENDING/编号/event_date → 人工修订+reanalyze 不覆盖+CONFIRMED → 时间轴关联 → 材料包条目+快照 content 逐字段 → 导出 DOCX/PDF 文本断言）；**M8 状态机真实闭环**（FAILED 直接解析 409 `INVALID_TRANSITION` → retry QUEUED → 再解析 422 `PARSE_FAILED` → FAILED 且错误信息保留）；mock OCR 空文本行为固化（M5/M6/M7）；M11 下载头 ASCII 回退 `v2.pdf` + `filename*` 精确还原。
- 后端修复：`routes/analysis.py` analyze 端点把 `FileServiceError` 转 409 错误信封（此前 FAILED 文件直接解析返回 500）。
- 脚本修正：错误信封断言初版误用 FastAPI 默认 `detail.code`，与本项目全局 `error.code` 信封不符，改为对 BODY 子串断言（与 `e2e-material-packages.sh` 惯例一致）。
- 回归：`e2e-real-materials.sh` 全部通过、后端 **pytest 270 passed**、`e2e-smoke.sh` 全流程通过。
- 未做（按 9-D 边界）：9-D-3 人工走查、9-D-4 部署风险处置（Dockerfile/备份脚本，待批）、9-D-5 汇总报告、Git 提交。
