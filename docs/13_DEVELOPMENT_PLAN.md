# 开发计划

## Phase 0 — Specification
目标：
- 初始化仓库；
- 创建 docs；
- 创建 .env.example；
- Docker Compose。

## Phase 1 — Foundation
实现：
- Next.js；
- FastAPI；
- PostgreSQL；
- 用户认证；
- Case CRUD；
- 基础 UI。

验收：
创建案件并重新打开后数据仍存在。

## Phase 2 — File Management
实现：
- 批量上传；
- 文件列表；
- 文件预览；
- hash；
- 状态。

验收：
20 个文件上传成功，逐个可查看。

## Phase 3 — Parsing
实现：
- PDF parser；
- DOCX parser；
- OCR adapter；
- AI adapter；
- analysis job。

验收：
上传测试文件后生成结构化 analysis。

## Phase 4 — Evidence
实现：
- Evidence；
- Event；
- Person；
- Evidence links；
- 自动编号。

验收：
analysis 可以生成可编辑证据。

## Phase 5 — Review
实现：
- 双栏审核；
- 字段修改；
- confirm；
- retry；
- version protection。

验收：
用户修改不会被 AI 静默覆盖。

## Phase 6 — Timeline
实现：
- 时间轴；
- 事件编辑；
- 证据关联。

## Phase 7 — Export
实现：
- DOCX；
- PDF；
- ZIP；
- 页码；
- 编号。

验收：
完整证据包可以打开、顺序正确、页码正确。

## Phase 8 — Hardening
实现：
- 权限测试；
- 安全；
- 日志；
- 限流；
- AI evaluation；
- Docker production build。

### Phase 8-A3 — 证据缺口分析（材料缺口）
实现：
- 确定性规则（无 AI）：FACT_NO_EXPECTED_TYPE_SOURCE、EVENT_UNDATED_NO_ANCHOR；
- 期望类型映射覆盖 EvidenceType 封闭词表；
- service 层四道闸门：中性 → 无义务措辞 → 来源可追溯 → schema；
- 结果按版本不可变，gap_id 确定性 uuid5（跨版本指纹）；
- API：POST/GET/history 三端点；前端独立页面 + 历史版本。
- 明确跳过（设计决策）：EVENT_NO_EVIDENCE（避免与 A2 面板重复）、
  FACT_SINGLE_SOURCE（不作缺口）；空案件 400 不建行；v1 无闭环状态。

## Phase 9 — 仲裁材料包

### Phase 9-A — 基础层（已完成）
实现：
- `material_packages`（草稿 + `draft_version` 乐观锁）、`material_package_items`
  （顺序/编号唯一约束）、`material_package_snapshots`（不可变快照）；
- 跨案件证据引用拒绝（与不存在同码防探测）、并发保存 409、快照只读。
验收：28 个后端测试，`alembic check` 无漂移。

### Phase 9-B — 编排与审核页面（已完成）
实现：
- 列表/新建/三区域编辑页/历史快照/只读详情；脏标记与未保存双重拦截；
  409 版本冲突显式提示；鉴权 blob 预览；纯逻辑抽离 vitest；
- `scripts/e2e-material-packages.sh` 14 步真实 HTTP 端到端。
验收：14/14 步真实执行，前后端全绿。

### Phase 9-C — 成卷导出与状态放开（已完成）
实现：
- 决策 1：完整性附录仅中性「材料完整性提示」+ 开关（无 A1/A2，不输出
  review_status）；无 A3 成功结果 → 409 `GAP_APPENDIX_UNAVAILABLE`。
- 决策 2：发布 = 纯状态标记，发布后仍可编辑；仅 ARCHIVED 只读 → 409
  `NOT_EDITABLE`；有快照的草稿不可删（`HAS_SNAPSHOTS`）；空包不能快照
  （`EMPTY_PACKAGE`）。
- 决策 3：导出按快照渲染，未快照 → 409 `SNAPSHOT_REQUIRED`，记录
  snapshot_id/version。
- 决策 4：仅 PDF/DOCX（不产 ZIP）；逐条嵌入原始内容，不可转换显式标注，
  扫描页栅格化 cap 30/文件 + 截断注记。
- 决策 5：列表页 limit=100 + 超限提示（修复 20 条静默截断）。
- 决策 6：Playwright 11 场景 + 案件导出 401 裸链接改带鉴权下载。
- CORS 白名单（此前无 CORSMiddleware，浏览器跨源预检 405）。
- 修复编辑页 StrictMode 双重加载竞态（loadSeq 丢弃过期响应）。
- 脚本 venv 路径统一为 `backend/.venv`。
验收：后端 250 测试、Playwright 11/11、`e2e-smoke.sh`、
`e2e-material-packages.sh` 14/14、`alembic check` 全部通过。

### Phase 9-D — 真实材料端到端验证（9-D-1/9-D-2 已完成，9-D-3/9-D-4/9-D-5 进行中）
设计：`docs/16_PHASE_9D_DESIGN.md`（含风险登记册 R1-R12 与阶段划分）。

#### 9-D-1 脱敏材料套件（已完成）
- `scripts/make-real-materials.py`：运行时生成 13 份材料（M1-M12，含 M10a/b 两
  份伪装样本），覆盖 PDF 文本层/DOCX 表格/TXT/聊天形态/图片/扫描 PDF/损坏
  PDF/超大文件/改名攻击/中文文件名+分号/多页混合；输出 manifest（sha256 +
  逐份预期行为），二进制不入库。
- 脱敏规则：虚构姓名/单位，证件号与卡号为故意无效演示值，不生成二维码。

#### 9-D-2 自动化验证（已完成）
- `scripts/e2e-real-materials.sh`：对运行中后端的真实 HTTP 端到端验证：
  - M1-M12 逐份上传/解析/状态断言（M8 预期 FAILED；M9/M10a/M10b 拒绝原因）。
  - M1 七跳可追溯链：file sha256（DB==manifest==下载字节）→ analysis
    （provider/prompt_version/结构化字段）→ evidence（PENDING/编号/event_date）
    → 人工修订+reanalyze 不覆盖+CONFIRMED → 时间轴关联 → 材料包条目+快照
    content 逐字段 → 导出 DOCX/PDF 文本含编号/名称/拟证明事项/原文片段。
  - M8 状态机真实闭环：FAILED 直接解析 → 409 `INVALID_TRANSITION` → retry
    QUEUED → 再解析 422 `PARSE_FAILED` → 回到 FAILED 且错误信息保留。
  - mock OCR 空文本行为固化（M5/M6/M7：category=other、兜底摘要、PENDING）。
  - M11 下载头 ASCII 回退 `v2.pdf` + `filename*` 精确还原。
- 后端修复：`routes/analysis.py` 的 analyze 端点把 `FileServiceError`
  （如 INVALID_TRANSITION）转为 409 错误信封（此前 FAILED 文件直接解析 500）。
- 验收：`e2e-real-materials.sh` 全部通过；后端 pytest **270 passed**；
  `e2e-smoke.sh`、`e2e-material-packages.sh` 回归通过。
- 修正：脚本初版错误信封断言误用 FastAPI 默认 `detail.code`，与本项目全局
  `error.code` 信封不符，已按兄弟脚本惯例改为对 BODY 子串断言。

#### 9-D-3 人工走查（待执行）
按 `docs/16` §4 的 T1-T8 清单逐条记录通过/问题，只报有依据问题。

#### 9-D-4 部署风险处置（待批）
R1 两个 Dockerfile + R4 备份/恢复脚本，需用户批准后实施。

#### 9-D-5 汇总（待执行）
9-D 报告（材料验证矩阵/可用性问题清单/风险登记册含未验证标注）。

## AI Agent 工作规则

每个 Phase 完成后：
1. 运行 lint；
2. 运行 type check；
3. 运行 unit tests；
4. 运行 integration tests；
5. 修复所有阻断错误；
6. 更新 README/CHANGELOG；
7. 输出本 Phase 完成摘要。

不要跳过测试。
不要为了“通过测试”删除测试。
不要擅自扩大产品范围。
