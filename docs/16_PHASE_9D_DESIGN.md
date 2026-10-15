# Phase 9-D 实施设计（设计稿 · 未实施）

> 状态：待确认。本文件仅为方案设计，未包含任何代码改动。
> 事实分级：**[事实]** = 本环境实跑/实测确认；**[推断]** = 仅代码阅读得出、未运行验证；**[未验证]** = 本环境不具备验证条件。

## 0. 阶段目标与约束

验证现有劳动争议证据整理器能否使用真实格式的脱敏材料完成端到端流程，并评估产品是否具备进入小范围试用的条件。

约束：
- 不启动 Phase 10。
- 不添加 ZIP 打包或 A1/A2 附录。
- 不新增大规模 AI 法律分析能力。
- 不改变已通过验收的材料包核心业务规则。
- 不提交 Git。
- 优先复用现有功能，不做无必要架构重构。

---

## 1. 当前端到端流程及真实代码入口

| 环节 | 后端入口 | 前端入口 | 现有验证 |
|---|---|---|---|
| 注册/登录 | `routes/auth.py`（bcrypt+JWT，注册 5/60s、登录 10/60s 限流） | `app/login/page.tsx` | pytest `test_auth`/`test_security`；smoke 第 1 步 |
| 上传 | `POST /cases/{id}/files` → `services/files.py`；白名单校验在 `files/validation.py`：**仅 PNG/JPEG/PDF/DOCX/TXT**，扩展名+MIME+magic bytes 三重校验，单文件 25MB **[事实 config+validation]** | `cases/[id]/files/page.tsx`（批量上传、状态列表、重试、删除） | `test_files_*`、`test_threat_model`（改名攻击/SVG/HTML 伪装均拒绝）、smoke 第 5 步 |
| 解析+AI | `POST /cases/{id}/analyze` → `services/analysis.py::analyze_file`：`parse_document`（`parsers/documents.py`，PDF 文本层优先、无文本层转 OCR；DOCX 段落+表格；TXT UTF-8 容错；图片仅 OCR）→ AI provider（默认 **mock**：`ai/rules.py` 确定性分类/抽取 + `ai/mock.py`）→ `DocumentAnalysis` 落库（provider/model/prompt_version/confidence） | files 页「全部解析」按钮 | `test_analysis_api`、`test_ai_unit`（含 corrupt PDF、无 OCR 图片不报错）；smoke 第 6-7 步 |
| 证据生成 | `suggest_evidence_from_analysis`：**自动建 Evidence，状态 PENDING**，confidence<0.80 强制进人工队列，proof_purpose 永远待人工 **[事实 analysis.py:151-220]** | `review/page.tsx`（左原件右 AI+人工并列）、`evidence/page.tsx`（分类/证明目的/「待确认→已确认」徽标） | smoke 第 8-10 步（含"人工修改不被重新解析覆盖"） |
| 时间轴 | `POST /cases/{id}/events/build` → `services/timeline.py` | `timeline/page.tsx`（改日期、合并、删除） | smoke 第 11 步 |
| 材料缺口 A3 | `routes/evidence_gaps.py` + `services/evidence_gaps.py`（两条规则 `FACT_NO_EXPECTED_TYPE_SOURCE`/`EVENT_UNDATED_NO_ANCHOR`，中性措辞闸门） | `evidence-gaps/page.tsx` | smoke 第 14 步、pytest 30 例 |
| 材料包/快照/导出 | 9-A/B/C 全链路（`material_packages.py`、`export.py`） | 材料包 6 个页面 | 9-C 验收：270 pytest、12 Playwright、两个 shell e2e |
| 案件导出 | `POST/GET /cases/{id}/exports`（DOCX/PDF/ZIP——**ZIP 仅案件导出有，材料包没有**） | `cases/[id]/export/page.tsx` | smoke 第 12-13 步、`test_export` |

已知流程性事实（影响 9-D 设计）：
- **mock OCR 恒返回空文本**（`mock.py:284-286`，`test_ai_unit` 明确断言"图片无 OCR → 空文本不算错"）→ 纯图片材料在当前环境下会走完管道但**提取不到任何文字**，证据靠人工录入。**[事实]**
- 分析成功后**自动创建 PENDING 证据**，不是等用户手动建。**[事实]**
- 前端 18 个页面；全局免责声明在 `layout.tsx:31`（"仅供参考，不构成正式法律意见"）。**[事实]**
- 现有脚本已有一个"迷你材料套件"：`e2e-smoke.sh:45-65` 用 Python 现场生成 TXT/PDF/DOCX 各 1 个——但**没有图片、没有聊天记录形态、没有失败样本**。**[事实]**

---

## 2. 脱敏测试材料设计与验收标准

### 2.1 设计原则
- **只用白名单格式**（PNG/JPEG/PDF/DOCX/TXT），不因材料扩展功能；HEIC/XLSX/音视频/CSV 一律不纳入材料集，只在报告中记录"当前不支持"。
- **运行时生成，不入库二进制**：仿照 smoke 的做法，新增生成器脚本现场产出到临时目录（避免往 git 仓库塞真实感图片）。
- 脱敏规则：虚构姓名（张三/李四）、虚构单位（某某科技）、身份证/银行卡/手机号只用**故意无效的演示值**、二维码/条码不生成、聊天双方用 A/B 称谓。

### 2.2 材料矩阵（建议 12 份，覆盖 5 类输入 + 4 类异常）

| # | 材料 | 格式 | 覆盖点 | 验收标准 |
|---|---|---|---|---|
| M1 | 劳动合同（文本层） | PDF | 正常 PDF 抽取 | 上传 200→解析 SUCCESS→自动证据含入职日期/月工资（rules 抽到日期+金额）→人工可改→导出正文含原文 |
| M2 | 工资条明细 | TXT | 纯文本、金额多 | 同上；金额抽取 ≥3 条 |
| M3 | 聊天记录导出（长文本） | TXT | 聊天形态分类 | mock 分类器判为 chat 类→低置信进待确认队列 |
| M4 | 考勤表 | DOCX | 表格抽取 | 表格单元格进 extracted_text；导出含表格文本 |
| M5 | 聊天截图 | PNG | 图片路径 | 上传+解析 SUCCESS 但**提取文本为空**（mock OCR）→证据靠人工录入→不阻断后续流程；记录此表现 |
| M6 | 工资条照片 | JPEG | 同上 | 同 M5 |
| M7 | 扫描版 PDF（整页图片无文本层） | PDF | PDF→OCR 回退 | `used_ocr=true`、文本为空（mock）、不报错；记录 |
| M8 | 损坏 PDF | PDF | 失败路径 | 解析 FAILED、状态可重试、错误信息可见 |
| M9 | 超 25MB 文件 | TXT | 体积拒绝 | 413/422 明确报错 |
| M10 | 改名攻击（HTML 改 .txt / 脚本改 .png） | TXT/PNG | 安全 | 拒绝（threat model 已有，材料集复验） |
| M11 | 中文文件名+空格+分号 | PDF | 文件名链路 | 上传/下载头正确（9-C 已验，回归即可） |
| M12 | 多页混合 PDF（2 页文本+1 页扫描） | PDF | 逐页 OCR 回退 | 文本页正常、扫描页空、合成不失败 |

### 2.3 可追溯性链（验收核心）
对 M1 完整断言一条链：`storage_key → file 行 → analysis 行(provider/prompt_version) → evidence 行(编号/proof_purpose/CONFIRMED) → 时间轴事件(关联证据) → 材料包条目(display_number) → 快照 content → 导出 DOCX/PDF 文本`——每跳用 API 响应字段比对，导出文本用 pymupdf/python-docx 断言包含该证据的编号、名称、拟证明事项与原文片段。

---

## 3. 自动化 vs 人工验证

| 自动化（脚本/pytest，可进回归） | 必须人工（9-D-3 走查） |
|---|---|
| 材料矩阵 M1-M12 的上传/解析/状态断言（新 shell 脚本，HTTP 级） | 各页面"第一眼能否看懂要干什么"（P0 劳动者视角） |
| 可追溯性链 API+导出文本断言（§2.3） | 导出 PDF/DOCX **视觉**质量（中文字体、分页、图片纵横比、表格可读性） |
| 失败/拒绝样本断言（M8-M10） | 聊天截图/照片在导出卷宗里的**可读性**（栅格化 30 页 cap 的实际观感） |
| 人工修订不被覆盖、确认流、限流 429（已有测试，回归） | 错误信息是否给出"下一步该点哪里"（逐条错误路径过一遍） |
| mock OCR 空文本行为固化成断言（防止未来回归） | AI 结果"待核实"标注的**感知**是否足够（徽标已有，措辞是否够醒目——只报有依据的问题） |
| 上传下载文件名、鉴权下载（9-C 已有，回归） | 发布/快照/归档名词对普通用户是否可区分 |

---

## 4. 可用性问题检查清单（走查用，逐条记录"通过/问题+证据"）

按 P0 用户任务流组织，只记录有明确依据的问题，不做视觉重构：

1. **T1 首次进入**：登录→建案件→上传，是否无需文档就能完成；空态文案是否指向下一步（如"还没有材料包。"→"新建材料包"）。
2. **T2 资料库**：文件状态词（待确认/解析中/失败…）是否可懂；"重试"出现在何时。
3. **T3 审核台**：左右分栏关系、"这个字段已由你修改，后续 AI 解析不会覆盖它"（`review/page.tsx:205`）是否被注意到；<0.80 强制审核是否有解释。
4. **T4 证据目录**：PENDING→CONFIRMED 徽标（`evidence/page.tsx:157`）；证明目的留空的后果提示。
5. **T5 时间轴**：日期可空的含义；合并的不可逆性是否有提示（confirm 有无）。
6. **T6 材料包**：草稿/快照/发布/归档四词区分（9-C 已知发布仅是标记——用户是否会误以为"发布=锁定"）；分歧提醒可见性。
7. **T7 导出**：卷宗 PDF 与原始材料的对应关系；免责声明位置。
8. **T8 全局**：AI 产出是否处处可辨认为"待核实建议"（后端 PENDING+前端徽标+layout 免责声明三层 **[事实]**，人工判断是否足够）；错误信封的 message 是否可执行（抽样：上传拒绝、409 `VERSION_CONFLICT`、`SNAPSHOT_REQUIRED`——后者已有引导文案 **[事实]**）。

---

## 5. 部署、安全与环境阻塞清单（风险登记册）

| # | 风险 | 严重度 | 触发条件 | 验证方法 | 建议顺序 |
|---|---|---|---|---|---|
| R1 | **compose 引用的 `backend/Dockerfile`、`frontend/Dockerfile` 不存在**，`docker compose up` 必失败 **[事实：目录已列]** → **9-D-4 已补写两个 Dockerfile + compose 补 build.args（NEXT_PUBLIC 需构建期内联）；静态评审通过；本环境无 docker，容器实际构建/运行仍标"未验证"** | 高 | 任何容器化部署 | 已完成静态评审；容器实跑留待有 Docker 的环境 | 1 |
| R2 | Docker/compose 从未执行过 **[事实 README 自述]** → **9-D-4：静态评审发现 compose 引用不存在文件的问题（R1）已修复；Docker 构建本身仍"未验证"** | 高 | 部署 | 静态评审；实跑留待外部环境 | 随 R1 |
| R3 | `SECRET_KEY`/compose 回退值 `change-me-in-production`，dev 库口令 `leo_dev_pw` 写死在 compose **[事实]** | 高 | 生产启动 | 代码评审+启动检查清单（可在 lifespan 加生产环境缺 secret 拒绝启动——**属改动，待批**） | 2 |
| R4 | **无任何备份/恢复脚本或文档**（grep 无命中 **[事实]**）——真实材料一旦试用即不可恢复 → **9-D-4 已补 `scripts/backup.sh`/`scripts/restore.sh`，并本机真实演练通过（marker 注入→备份→删除→恢复→逐行核对一致）** | 高 | 试用开始前 | 已完成演练并记录于 docs/17 §13 | 1 |
| R5 | S3 后端**装不上也测不了**：`boto3` 不在 requirements **[事实]**，S3Storage 全部 `pragma: no cover` | 中 | 切 `STORAGE_BACKEND=s3` | 需要真实桶；本环境不可验，只记录 | 3 |
| R6 | `JOB_BACKEND=rq` 路径（compose 的 worker 服务）**从未在本环境执行**（全程 inline）**[事实]** | 中 | 容器部署 | 本机装 redis 可部分验证；否则记录 | 3 |
| R7 | 真实 AI/OCR Provider 从未接入（只有 mock）**[事实]**；图片材料因此无文字 | 中 | 试用体验核心 | 属"不新增 AI 能力"边界外，只记录+在材料报告如实呈现 | 记录 |
| R8 | JWT 有效期 24h、无刷新、token 存 localStorage **[事实 config+api.ts]**；XSS 即令牌失窃 | 中 | 有 XSS 或共用设备 | 代码评审；CSP 已设且 `script-src 'self'` **[事实]**，风险部分缓解 | 3 |
| R9 | 限流计数在进程内存 **[推断 rate_limit.py]**，多副本部署时限流失效 | 低 | 横向扩容 | 代码评审即可 | 4 |
| R10 | compose 无 HTTPS/反代 **[推断（文件内无相关服务）]** | 中 | 公网试用 | 部署层解决，记录 | 4 |
| R11 | 日志脱敏已实现且有测试 **[事实 test_security]**；生产日志落盘/收集 **[未验证]** | 低 | 生产 | 检查清单项 | 4 |
| R12 | 容器内文件权限、pgdata/storage 卷权限 **[未验证]** | 低 | 容器运行时 | 依赖 R1 落地后验证 | 4 |

原则：以上未验证项在任何对外材料中一律标注"未验证"，不写成"已具备"。

---

## 6. 分阶段实施顺序、预计改动文件与回归计划

> 全部为**建议**，等确认；9-D-4 的两类改动（Dockerfile、备份脚本）超出"只评估不写码"字面范围，需单独批准。

| 阶段 | 内容 | 预计改动 | 回归 |
|---|---|---|---|
| **9-D-1 材料套件** | 生成器产出 M1-M12 + 材料矩阵文档 | 新增 `scripts/make-real-materials.py`（仿 smoke 内嵌 Python，输出到 `$TMP`）；`docs/12` 或本文档补矩阵 | 生成器自校验（文件存在、magic 正确） |
| **9-D-2 自动化验证** | HTTP 级全流程脚本：逐份上传→解析→断言状态→M1 可追溯链→失败样本→导出内容比对；mock OCR 空文本行为固化 | 新增 `scripts/e2e-real-materials.sh`；如需，补 `backend/tests/test_parsers_real_fixtures.py`（小） | 新脚本 + 既有全量（见下） |
| **9-D-3 人工走查** | 按 §4 清单过 T1-T8，产出问题清单（截图路径/页面路由/复现步骤），只报有依据问题 | 仅文档：走查记录（并入 9-D 报告） | 无代码回归 |
| **9-D-4 部署风险处置（待批）** | R1 补两个 Dockerfile + compose 校验；R4 备份/恢复脚本+演练记录 | `backend/Dockerfile`、`frontend/Dockerfile`、`scripts/backup.sh`/`restore.sh`、README 部署节 | compose 静态评审；备份脚本本机真实演练一轮 |
| **9-D-5 汇总** | 9-D 报告：材料验证结果矩阵、可用性问题清单、风险登记册（含"未验证"标注） | `CHANGELOG`/`README`/`docs/13` 同步 | 全量回归一遍收尾 |

每阶段收尾固定回归（与 9-C 同口径）：`pytest -q`（270+）、`npm test`、`tsc`、`npm run lint`、`next build`（跑完重启 dev 前端）、`e2e-ui.sh`（12）、`e2e-smoke.sh`、`e2e-material-packages.sh`、`alembic check`。

---

## 7. 完成判定标准（DoD）

| 工作项 | DoD |
|---|---|
| 材料套件 | 一条命令生成全部材料；生成器本身在回归中可重跑；矩阵文档含"预期行为 vs 实际行为"两列 |
| 自动化验证 | `e2e-real-materials.sh` 真实跑通并打印逐项 ✅；M1 可追溯链 7 跳全部 API/导出断言；M8-M10 失败样本断言；mock 图片空文本表现被固化为断言 |
| 人工走查 | T1-T8 每项有"通过/问题"结论；每个问题附路由+复现步骤+严重度；无"感觉不好"类无依据项 |
| 风险评估 | 风险登记册覆盖 R1-R12，每项含严重度/触发/验证方法/顺序；**所有未验证项显式标注** |
| （待批）Dockerfile | compose 引用文件存在；静态评审通过；外部有 docker 的环境可执行（本环境只能交付到静态评审） |
| （待批）备份恢复 | 本机演练：备份→销毁测试库/存储目录→恢复→关键数据比对通过，演练记录入报告 |
| 收尾 | 全量回归绿；CHANGELOG/README/docs 同步；输出 9-D 完成报告后停止 |

---

## 8. 需要确认的决策点

1. **9-D-4 是否纳入本阶段**：补写两个 Dockerfile + 备份/恢复脚本（compose 目前引用不存在的文件，属硬伤；备份是真实材料试用的前置条件）。建议纳入，但等点头。
2. **材料矩阵 12 份是否够**：尤其 M5-M7（图片在 mock OCR 下只有"空文本不崩溃"可验）——如需验真实 OCR 效果，需提供可用的 OCR provider 凭证（超出"不新增 AI 能力"边界，不会自行添加）。
3. **走查产出位置**：并入 9-D 报告（推荐，不新增文件），还是单独成文。

确认后按 9-D-1 → 9-D-2 → 9-D-3（→9-D-4 如批准）→ 9-D-5 顺序实施。

---

## 附：问答记录（按用户要求，此后每次回答同步写入本文件）

### 2026-10-13 用户：以后回答都写进去
已确认：此后本会话中的每次回答，除在对话中输出外，同步追加写入本节下方，按时间倒序或顺序追加记录。

### 2026-10-13 回答：9-D-3 走查（T1-T8）执行结果

完整记录：`docs/17_PHASE_9D3_WALKTHROUGH.md`（证据在 `walkthrough-9d3/`）。

**结论：走查完成，PASS=37 / ISSUE=2 / MANUAL=2。**

1. **环境先修复**：容器重建导致 venv、node_modules、PostgreSQL 全丢（备份排除项），
   已重装并跑通迁移；另修两处缺陷——
   - `requirements.txt` 缺 `email-validator`，README 快速开始装完依赖即 `ImportError`
     （已补，全新 venv 验证 `import app.main` OK）；
   - 容器 locale 缺失（`en_US.UTF-8` 未生成）导致 Playwright `setInputFiles` 对
     **中文路径静默丢文件**，走查在 T2 卡死（`locale-gen` 修复；建议登记为 R13）。
2. **通过项**：T1 首次进入、T2 资料库状态与重试、T3 人工修订不覆盖提示、
   T3b 低置信「置信度低，请人工确认」、T4 双态徽标/已人工修改/证明目的编辑、
   T6 材料包四词区分与「发布≠锁定」（确认框+发布后仍可编辑）、T7 无快照指引→写条目→
   建快照→UI 生成 PDF→**真实下载并文本校验**（编号、拟证明事项、中文非乱码、
   与人工修订值一致）、T8 免责声明与上传拒绝原因。
3. **两个有依据的问题（未改代码）**：
   - **P2** `/cases/{id}/timeline` 合并事件无确认、点击即不可逆（`timeline/page.tsx:100`，
     删除事件 `:90` 却有 confirm）；
   - **P3** `/cases/{id}/evidence` 证明目的留空无任何后果提示（空值整块渲染消失）。
4. **回归全绿**：pytest 270 passed；lint / typecheck / vitest 22；Playwright 12 passed；
   `e2e-real-materials.sh`、`e2e-smoke.sh`、`e2e-material-packages.sh`、`alembic check`
   全部通过（`next build` 留到 9-D-5 停服后跑）。
5. **仍需人工**：卷宗排版观感（`walkthrough-9d3/t7-材料包卷宗.pdf`）；
   409 `VERSION_CONFLICT` 的浏览器文案（后端测试已过，前端仅代码检查）。

下一步等你选择：先修 §3 两条问题，或直接进入 9-D-4（部署风险处置，需批准）。

### 2026-10-13 回答：9-D-3a/3b 修复与补齐人工验证（授权指令执行完毕）

用户授权顺序：9-D-3a → 9-D-3b → 9-D-4 → 9-D-5。本轮完成 3a/3b，**等待确认后再进 9-D-4**。
完整记录：`docs/17_PHASE_9D3_WALKTHROUGH.md` §8-§11。

**9-D-3a（两个走查问题已修）**
1. P2 合并确认：`timeline-ui.ts` 新增 `buildMergeConfirmMessage`（列出受影响事件标题+日期、
   合并后果、**不可撤销**）+ `timeline/page.tsx` 在 `api.mergeEvents` 前 `window.confirm`，
   取消直接 return（不发请求、不改数据）。单测 `timeline-ui.test.ts`。
   顺带发现并修复后端缺陷：merge 端点**从未 commit**（`get_db.close()` 生产回滚，单测因共享
   session 假通过）；已补 `db.commit()` + 独立 session 回归测试。
2. P3 空证明目的提示：`evidence/page.tsx` 非编辑态显示「尚未填写拟证明事项，可编辑补充」+
   编辑快捷入口，编辑态 placeholder；有值时原样显示。不改数据结构/材料包规则。

**9-D-3b（补齐人工验证）**
1. PDF 逐页视觉检查（PyMuPDF 渲染看图，不只文本抽取）：3 页卷宗，中文字体（STSong-Light）、
   目录表格、正文分页**均正常**；**发现新问题 P3**——页脚「第 X 页 / 共 Y 页」的 Y 错误
   （`export.py:77` 把当前页码当总页数，3 页文档每页都写「共 N 页」N=本页码）。
   已定位根因，**未修**（超出 3a 授权范围，待你决定）。
2. 浏览器实测 409 VERSION_CONFLICT：双标签页同开编辑页，A 保存后 B 保存 → API **409** +
   UI 提示「材料包已被其他人修改…本次保存未生效」+「重新加载」按钮 + 服务端 draft_version
   未被推进。此前 docs/17 §6 的「未验证」项已闭环。

**回归全绿**：pytest **271 passed**（+1 commit 回归）｜lint/tsc/vitest **23**｜Playwright **12**｜
`e2e-smoke.sh` / `e2e-material-packages.sh` / `e2e-real-materials.sh` / `alembic check` 全通过｜
走查重跑 **PASS=44 / ISSUE=0 / MANUAL=2**。

**待你决定的剩余问题**：PDF 页脚总数 bug（P3，根因已定位在 `export.py:77`，修法为两遍 build
或 canvas 计数）。是否随 9-D-4 一起修，或单独修，或不修？

### 2026-10-13 回答：9-D-3c 修复 PDF 页脚总页数错误（P3）；获准进入 9-D-4

用户指令：先修 P3 页脚，回归清单跑完出报告，再进 9-D-4。已完成，记录见 `docs/17` §12。

**修复**：根因是 `export.py:_page_footer` 拿 `doc.page`（build 期间=当前页码）当总页数。
改为 `_page_footer(total_pages)` 工厂 + `_build_pdf(story_factory)` 两遍构建
（第一遍渲临时 buffer 数页数 `probe.page`，第二遍写真实总数；footer 画在页边距内不占
flowable 空间，两遍分页一致）。`render_pdf` 与 `render_package_pdf` 均改用；导出内容
结构不变、不换框架；DOCX 无页码 footer 不受影响。

**测试**：新增 `test_pdf_footer_shows_true_total_page_count`（2 材料→3 页：每页「共 3 页」+
第 1/2/3 页各自「第 N 页 / 共 3 页」）；强化案件导出逐页断言。

**回归（全部实跑）**：pytest **272 passed**（+1 页脚用例）｜tsc 0｜lint 0｜vitest **23**｜
Playwright **12**｜`e2e-smoke.sh` 通过｜`e2e-material-packages.sh` 14 步通过｜
`alembic check` 无漂移。

**下一阶段**：已按授权进入 **9-D-4 部署风险处置**（R1 补 `backend/Dockerfile`、
`frontend/Dockerfile` + compose 静态评审；R4 新增 `scripts/backup.sh`/`restore.sh`
并本机真实演练一轮）。9-D-4 完成后是 9-D-5 汇总。

### 2026-10-14 回答：9-D-4 完成（R1 Dockerfile 补写 + compose 静态评审；R4 备份/恢复脚本+真实演练）

按批准范围完成，未改 R3/R6 等范围外风险：

- **R1**：新增 `backend/Dockerfile`、`frontend/Dockerfile`（含 `.dockerignore`）。
  compose 静态评审发现并修复：frontend 缺 `build.args.NEXT_PUBLIC_API_BASE_URL`
  （Next 构建期内联，仅 runtime env 无效）。`yaml.safe_load` 通过。
  确认 R6：worker 服务命令引用 `rq` 但依赖未装、代码零引用——**按现状无法启动，仅登记不修**。
- **R4**：新增 `scripts/backup.sh`/`scripts/restore.sh`；本机真实演练一轮
  （marker 注入→备份（db.dump 168K + storage.tar.gz 909M）→删除→恢复→行数与
  字节级内容核对一致→清理回基线）。演练记录见 `docs/17` §13。
- 风险登记册 R1/R2/R4 已更新为"已处置/已演练"；R3/R6/R10/R12 维持原状待批。

**下一阶段**：9-D-5 汇总（9-D 报告 + 全量回归一遍 + `next build`）。

### 2026-10-14 回答：9-D-5 完成（全量回归 + next build + 汇总报告）；Phase 9-D 完结

- 全量回归收尾全绿：pytest **272**、tsc/lint 0、vitest **23**、Playwright **12**、
  e2e-smoke / e2e-material-packages / e2e-real-materials（M1-M12+七跳链）通过、
  走查 **PASS=44 / ISSUE=0 / MANUAL=2**、alembic check 无漂移。
- **`npm run build` 首次实跑通过**（17 个路由，首屏共享 JS 87.2 kB）；构建覆盖了 dev
  `.next` 后重启 dev server 复核走查仍 PASS。
- 汇总报告写入 `docs/18_PHASE_9D_FINAL_REPORT.md`：材料矩阵 M1-M12 逐份预期 vs 实际
  全通过（M3 置信度按实际 0.96 修正）；可用性问题 U1-U8（U1-U3 已修，其余记录）；
  风险登记册 R1-R13 现状（R1/R2/R4 已处置/已演练，R3/R5/R6/R8-R12 待批或记录）；
  试用决策建议（单机+内网+先备份+明示 U4/U7 可试用）。
- **Phase 9-D 完结**，不启动 Phase 10，不提交 Git（按边界）。

### 2026-10-14 回答：9-D-5.1 收尾确认 + Phase 9-D 最终封版

用户指令：仅复核 P3 页脚总页数（不扩范围、不改材料包规则），补 PDF 视觉检查和 export
回归，输出封版记录；不进 Phase 10，Docker/S3/RQ/真实 AI Provider 保持待办。

- 该缺陷已在 9-D-3c 修复；本次**零新改动**，仅复核：export 回归 **32 passed**；
  实时 HTTP 生成 4 页卷宗、PyMuPDF 渲染逐页断言「第 N 页 / 共 4 页」通过；人工看图
  page1/page4 页脚正确。
- **Phase 9-D 最终封版记录**写入 `docs/18` §8。

### 2026-10-14 回答：修复 Hugging Face Spaces 浏览器访问卡在"正在跳转…"

用户在 HF Spaces 云工作站浏览器访问前端时根路由卡在"正在跳转…"。根因：Next.js 输出
绝对路径 `/_next/...`，浏览器请求主机根路径命中 code-server 而非 Next.js → JS 全 404
→ 根路由 `router.replace("/cases")` 不执行。本地直连 `127.0.0.1:3000` 实测正常，仅
code-server `/proxy/3000/` 前缀路径坏。

**修复方案**（同 OpenClaw Control UI 代理模式）：
1. `frontend/next.config.js`：`basePath` 由 `NEXT_PUBLIC_BASE_PATH` 注入；`distDir`
   由 `NEXT_DIST_DIR` 注入（隔离本地 :3000 与代理 :3002 的构建缓存）。
2. `frontend/code-server-proxy.mjs`（新建）：监听 :3001，给被 code-server 剥掉的
   路径补回 `/proxy/3001`，转发到 :3002；含 WebSocket upgrade 转发（HMR）。
   修复 trailing-slash 重定向放大问题（Next.js basePath 对 `/proxy/3001/` 308 到
   `/proxy/3001`，code-server 再拼前缀成 `/proxy/3001/proxy/3001`）——bare `/`
   直接映射到无斜杠 basePath，避免重定向。
3. 代理实例 :3002 启动参数：
   - `NEXT_PUBLIC_BASE_PATH=/proxy/3001`（资产 URL + 客户端路由带前缀）
   - `NEXT_PUBLIC_API_BASE_URL=/proxy/8000/api/v1`（浏览器 fetch 经 code-server
     到后端，同源免 CORS）
   - `NEXT_DIST_DIR=.next-proxy`
4. `scripts/start-frontend-proxy.sh`（新建）：一键启动 + 冒烟测试。
5. `lib/api.ts` 无需改动——`NEXT_PUBLIC_API_BASE_URL` 覆盖默认值即可。

**验证**（经 code-server :7860 模拟真实浏览器路径）：
- `GET /proxy/3001/` → 200，HTML 资源带 `/proxy/3001/_next/...` 前缀
- `GET /proxy/3001/_next/static/chunks/webpack.js` → 200
- `GET /proxy/8000/healthz` → 200（API 同源可达）
- Playwright 端到端：注册 → 201 → token 写入 localStorage → 客户端跳转
  `/proxy/3001/cases` → 案件列表 200，零 JS 错误
- 本地 `:3000` 直连不受影响（`NEXT_PUBLIC_BASE_PATH` 未设时 basePath 为空）

**可访问 URL**：`https://lldakjd-aa.hf.space/proxy/3001/`

**边界**：不进 Phase 10；Docker 实跑 / S3 / RQ / 真实 AI Provider 仍待办。

---

## 追加记录（2026-10-14 会话：真实 AI 接入 + 布局改造）

### Q: Modal API 返回 `missing forward secret`，怎么接入真实 AI？
A: Modal 的 Envoy 代理层强制 mTLS，不可绕过；HF token 无推理权限；
`ANTHROPIC_BASE_URL=ai2.hhhl.cc` 返回 521。最终方案：本地 kiro 免费代理
（`/root/.openclaw/workspace/opencode-kiro-freeapi/server.mjs`，:6449，
key `free-proxy-key`，28 个免费模型）。后端新增 `OpenAIProvider`
（`backend/app/ai/openai_provider.py`）适配 OpenAI 兼容接口，遵循
docs/08_PROMPT_SPEC 的中文 JSON schema prompt，失败回退 MockAIProvider。
`.env`：`AI_PROVIDER=openai`、`AI_BASE_URL=http://127.0.0.1:6449`、
`AI_MODEL=kilo-auto/free`。两个案件（张伟 10 文件、a公司 1 文件）均真实 AI 分析成功；
PNG 无文本层走 mock 兜底。上游偶发 502 会触发回退，需重跑分析。

### Q: 上传同一文件再次分析会产生重复证据吗？
A: 会。修复：`analysis.py` 的 `suggest_evidence_from_analysis` 按
`source_file_id` 查最新 Evidence，存在则更新（用 `edited_fields` 属性保护
用户已编辑字段），不新建行。中文日期（如"2022年3月1日"）解析为 ISO。

### Q: 案件缺材料时缺口引擎能否检出？
A: 可以。`evidence_gaps.py` 的 `_FACT_PATTERNS` 增加叙述文格式正则
（`入职时间[：:为是]`、"于X年X月X日入职"、"月工资X元"等）。
a公司违法解除案件（1 份聊天记录）检出 **5 项缺口**：入职时间/合同开始
时间/岗位/用人单位/薪资，UI 显示完整来源与搜索依据。张伟案 0 缺口是
正确结果（3 facts 全被覆盖，证据齐全）。

### Q: 案件子页面滚动体验怎么统一？
A: 新建 `cases/[id]/layout.tsx`：左侧常驻侧边栏（概览/资料库/审核工作台/
时间轴/证据目录/材料缺口/材料包/导出中心 + BackLink 返回案件列表），
内容区 `h-[calc(100vh-120px)] overflow-y-auto` 统一容器内滚动。
各子页面不再各自滚动，避免双滚动条。

### Q: 资料库上传区被滚动带走怎么办？
A: 把标题+上传区+通知条包进 `sticky top-0 z-10 bg-white` 容器，
文件列表在其下方独立滚动。Playwright 滚动 600px 后上传区仍固定在
y=135，验证通过。

### Q: 材料缺口页历史版本怎么切换？
A: 底部列表改为顶部下拉框 `#gap-version-select`（"最新版本 (vN)" +
历史版本），`selectedId` state 控制，结果区在统一滚动容器内。

### Q: 平台侧（HF Spaces）还有什么遗留？
A: 3002 前端进程曾挂死导致"一直显示加载中"，已重启修复
（`setsid nohup ... < /dev/null &` 后台启动 + 轮询验证）。
kiro 代理当前手动启动，可做开机自启。待批项不变：R3 SECRET_KEY、
R6 rq worker、R10 HTTPS、R12 卷权限；无 docker（R1/R2）。

**测试**：后端 271 全过；前端 `tsc --noEmit` 0 错误 + vitest 23 全过。
**本轮改动未提交**（openai_provider / registry / config / evidence_gaps /
analysis 去重 / BackLink / layout / evidence-gaps / files sticky / cases 重写）。

### Q: 案件叙述怎么生成？（AI 生成案件叙述）
A: 之前 `description` 只是手工字段（测试假数据）。新增 AI 生成链路：
- `POST /cases/{id}/narrative`（routes/cases.py，同步 def 走线程池，
  `asyncio.run` 调 LLM，同 analysis 路由契约）→ 汇总证据摘要+时间轴事件
  构造 prompt（services/narrative.py，事实性、时序、禁法律评价，
  300-500字）→ `OpenAIProvider.generate_text`（新增自由文本方法，
  不进 Protocol，缺省即回退）→ kiro :6449 真实生成（~9s）。
- **只返回草稿不落库**：前端填入 textarea，用户检查后点「保存」走
  PATCH，AI 永不静默覆盖人工叙述；已有文本时先 confirm。
- LLM 不可用回退 `template`：按时间排的事件+证据摘要拼接
  （provider="template"）。无材料 409 NO_MATERIALS。
- 验证：真实 AI 生成 386 字叙述（读的是库里证据摘要，与上传材料一致）；
  Playwright 点击→生成→保存→刷新持久化通过；后端 275 测试
  （新增 3：无材料 409 / 模板路径+不落库 / 越权 404）全过。
- 同批：导出中心历史导出加「查看」（带 token blob 新标签，
  headless 验证 %PDF 魔数）/「删除」（DELETE /exports/{id}，
  删存储对象+审计 EXPORT_DELETED+commit——首版漏 commit 导致
  204 但行还在，已修）；案件概述页叙述 textarea（≤5000 字实时计数）。

### Q: 能出 Windows 绿色免安装版吗？（便携版打包）
A: 可以。选型：**绿色便携版优先**（解压即用、自选目录=解压位置、
数据全在包内 data/），一键安装包（Inno Setup）留作后续。
技术路线：embeddable Python 3.11.9 + Windows node.exe + next standalone，
在 Linux 上构建出 `dist/labor-evidence-portable-0.1.0-win64.zip`
（97 MiB，8529 文件）。

**SQLite 兼容改造**（SQLite/PG 双库测试均 275 全过）：
- `db.py`：连接级 PRAGMA（`foreign_keys=ON`——SQLite 默认关，级联删除会
  静默失效；`busy_timeout=5000`；`journal_mode=WAL`）+ `check_same_thread=False`；
  `create_schema()` 在 SQLite 建表时剥掉 `UNIQUE ... DEFERRABLE`
  （SQLite 不支持表级 deferrable，PG 走 alembic 不受影响）。
- `save_items()` 两阶段编号：先全部挪临时位（+1,000,000）再落 1..N——
  SQLite 逐语句即时查 UNIQUE，编号互换（1↔2）中途会撞车（PG 靠
  DEFERRED UNIQUE 挡住了这个）。
- `TimestampMixin` 改 Python 侧 `utcnow()`：SQLite `CURRENT_TIMESTAMP`
  仅秒级精度，同秒内快照变更检测不出 CHANGED；微秒精度两库一致。
- `export.py` Boolean `server_default` 改 `text("false")`（裸关键字，
  引号文本会被 SQLite 存成 'false' 字符串）。
- `conftest.py`：PG 专属 `TRUNCATE ... CASCADE` 在 SQLite 下改逆序 DELETE。
- 实测：无 PG 专属 SQL/fcntl 等平台绑定；python-magic 是 optional
  （无 libmagic DLL 自动降级）。

**打包脚本**（scripts/）：
- `build-portable.sh`：下载缓存官方 runtime → 改 `_pth` 启用
  `Lib\site-packages`+`import site` → pip 交叉装 win_amd64 wheels
  （`requirements-portable.txt`：pin 实测版本、去 psycopg/alembic/pytest/
  `uvicorn[standard]`——uvloop 无 win 轮子且 pip 环境标记按构建宿主求值；
  passlib 是 sdist-only，先本地 `pip wheel` 再装）→ `next build`
  （`output:"standalone"` + `NEXT_DIST_DIR=.next-portable` 隔离 dev 的
  `.next`；**static 必须拷到 server/.next-portable/static**——server.js
  内嵌构建时 distDir，常规 .next/static 做法只适用于默认 distDir）→
  生成 `.env`（production + 随机 SECRET_KEY + sqlite 相对路径 + mock AI
  注释模板）→ 4 个 bat + README → zip。
- `portable-smoke-test.sh`：宿主 python+node 跑同一 stage 树
  （包内 runtime 是 win 构建），首次建库→healthz→注册/登录/建案→
  登录页+`_next/static` 200；临时接管 8000/3000，结束自动恢复 dev。
  **两次踩坑**：① 密码策略禁键盘/数字序列（`smoke-test-pass-123` 被 422，
  换 `correct-horse-battery`）；② `pkill -f` 模式若出现在执行命令行里会
  自杀（脚本内执行无此问题，交互命令须用 `app[.]main` 括号技巧）。
- `start.bat`（幂等：先 stop 再起 + 首次 create_all + 开浏览器）/
  `start-backend.bat`、`start-frontend.bat`（嵌套引号地狱的替代）/
  `stop.bat`（netstat 按端口杀，尾随空格防误伤 30001）/
  `README.txt`（用户向）+ `README_技术说明.md`（构建者向）。

**验证**：build 两轮 exit 0；smoke 两轮 SMOKE OK；zip 抽验
（.env 随机密钥、_pth、uvicorn/passlib、node.exe、static 全在）；
dev 服务恢复 healthz ok + web 200。**Windows 实机未测**（bat/embed/
taskkill 按官方文档行为编写），需在真机跑 start→注册→上传→导出全链路。

### Q: 一键安装版怎么做？（NSIS）
A: `scripts/build-installer.sh` + `scripts/portable/installer.nsi.in`，
产出 `dist/labor-evidence-setup-0.1.0-win64.exe`（64MiB，LZMA solid，
252MB 载荷）。**选 NSIS 弃 Inno Setup**：ISCC.exe 只能 Windows/Wine 跑，
makensis（apt install nsis）在 Linux 直接交叉编译，功能等价——欢迎页/
组件页（桌面快捷方式可选）/自选目录/开始菜单/完成后启动/控制面板卸载项。
- 载荷=绿色版 stage 树（同源）：按用户安装无 UAC，默认
  `%LOCALAPPDATA%\Programs\LaborEvidenceOrganizer`（ASCII 路径规避
  embed python 的非 ANSI cwd 边界）；卸载 MessageBox 提醒 data 一并删除。
- 坑：Debian nsis 3.08 的 FileFunc `GetSize` 只有 5 参（无新版第 4 个
  字节结果），首版模板 6 参报 "requires 5 parameter(s)"，改为 3 结果变量。
- **验证**：makensis 编译 ✓；`file` = PE32 Nullsoft ✓；7z 列出全部
  7332 文件（python.exe/node.exe/server.js/.env/bat 全在）✓；
  **Wine 8.0 + Xvfb 静默安装**（`/S /D=C:\leotest`，26s）落盘结构完整，
  文件数与 stage 相等、cmp 抽验字节一致 ✓。
- **Wine 端到端启动不可行**：embeddable Python 在 wine console 里
  `init_sys_streams ... WinError 6`（wine ConHost/stdio 限制，重定向
  cmd 内部句柄也救不了；非包缺陷——宿主 python+node 对同一 stage 冒烟
  通过）。另两个 wine 特有现象：`timeout` 命令缺失（真机自带）、
  `start /min` 子控制台随主退出被连带杀（真机 start 开新 console 独立）。
  → 真机验证仍是发布前必做清单：安装向导 UI、start→注册→上传→导出、
  控制面板卸载。
- README.txt 增补两种发行形式说明与卸载章节；zip/exe 同批重建（内容
  同源），第三轮 portable-smoke OK。
