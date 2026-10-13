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
| R1 | **compose 引用的 `backend/Dockerfile`、`frontend/Dockerfile` 不存在**，`docker compose up` 必失败 **[事实：目录已列]** | 高 | 任何容器化部署 | 本环境无 docker，无法实跑；补写后只能静态评审+外部验证 | 1（需确认是否属本阶段范围） |
| R2 | Docker/compose 从未执行过 **[事实 README 自述]** | 高 | 部署 | 同上，标记"未验证能力" | 随 R1 |
| R3 | `SECRET_KEY`/compose 回退值 `change-me-in-production`，dev 库口令 `leo_dev_pw` 写死在 compose **[事实]** | 高 | 生产启动 | 代码评审+启动检查清单（可在 lifespan 加生产环境缺 secret 拒绝启动——**属改动，待批**） | 2 |
| R4 | **无任何备份/恢复脚本或文档**（grep 无命中 **[事实]**）——真实材料一旦试用即不可恢复 | 高 | 试用开始前 | 编写 `pg_dump`+storage 目录备份脚本并在本机演练恢复 | 1（建议与材料验证并行） |
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
