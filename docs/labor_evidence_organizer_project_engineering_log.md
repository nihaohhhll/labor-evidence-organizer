# Labor Evidence Organizer：项目问题、解决方案与开发流程

-   **文档用途：** 项目工程复盘、AI 编程协作规范、后续阶段交接
-   **进度基准：** 截至 2026-10-10 的对话记录
-   **状态说明：** Phase 8-A1、A2 已报告完成；A3 仍是设计阶段，尚未编码
-   **证据口径：**
    本文中的测试数字和仓库状态来自项目执行报告，未在此重新运行代码验证。

## 1. 项目目标与原则

Labor Evidence
Organizer（劳动争议证据整理器）帮助普通用户把合同、聊天截图、工资表、银行流水、考勤、公司通知等分散材料整理成可核对、可追溯、可打印的证据材料。

核心流程：上传资料 → 解析分类 → 提取事实/事件/人员及来源 → 人工核对 →
生成时间线和证据目录 → 导出。

基本原则：

1.  不把产品定位为"AI 律师"，不替用户下法律结论。
2.  原始文件不可被 AI 分析覆盖；原件、分析结果、人工处理状态分层存储。
3.  每个事实/提示尽可能追溯到来源材料，并保留摘录。
4.  "材料中未发现"不等于"现实中不存在"。
5.  分析结果版本化且不可变；可变的人工处理状态与分析快照分开。
6.  关键约束必须在可信的 service 编排层对最终产物执行。
7.  测试必须区分通过、失败、未运行和环境阻塞；不夸大验证结果。
8.  未经用户确认，不实现尚未定案的设计，不自动提交 Git。

## 2. 架构与开发阶段

### 技术方向

-   前端：Next.js、TypeScript、Tailwind CSS、shadcn/ui
-   后端：Python、FastAPI、Pydantic、SQLAlchemy
-   数据库/迁移：PostgreSQL、Alembic
-   文件存储：本地存储起步，后续可抽象为 S3 兼容存储
-   AI/OCR：通过 Provider 接口隔离具体供应商
-   文档生成：python-docx、ReportLab、PyMuPDF
-   测试：Pytest、Playwright
-   开发部署：Docker Compose

### 阶段路线

Phase 0 规格文档 → Phase 1 基础设施 → Phase 2 文件管理 → Phase 3 解析/AI
→ Phase 4 证据管理 → Phase 5 人工核对 → Phase 6 时间线 → Phase 7 导出 →
Phase 8 强化功能。

当前记录涉及 Phase 8-A1 事实摘要、Phase 8-A2 结构化分析、Phase 8-A3
证据缺口分析。

## 3. 典型问题、根因与修复

### 3.1 校验放在被检查的组件内部（A1）

**问题：** `MockSummaryEnhancer` 自己调用
`assert_neutral`，但测试替身可以先通过校验，再把输出改成"公司违法解除劳动关系。"，绕过约束。

**根因：** 被检查者同时控制校验与最终输出。

**修复：** 将 `assert_neutral` 移到 service 层，对最终成品执行校验。

**经验：** 关键安全/业务约束放在可信编排边界；用 monkeypatch
或恶意测试替身验证校验不能被绕过。

### 3.2 中文日期触发词只向右搜索（A1）

**问题：**
"于2022年10月入职"这种日期在触发词前的表达被漏掉；同一句多日期时也可能选错。

**修复：**
按触发词与日期的相对距离就近匹配，并覆盖触发词前后两种语序和多日期样例。

**经验：** 规则抽取要用真实语言样例验证，不可假设固定语序。

### 3.3 UUID 无法直接 JSON 序列化（A1）

**问题：** `summary_json` 为 JSONB，输出中包含
`uuid.UUID`，无法直接持久化。

**修复：** 在 enhancer 输出边界把 UUID
转为字符串，并用集成测试验证实际写入数据库成功。

**经验：** 对 UUID、日期时间、Decimal、枚举等类型制定统一 JSON
转换规则。

### 3.4 移除应用层判空后测试仍全绿（A1）

**问题：** 移除 Python 侧"无事实则失败"后测试仍通过，因为数据库约束
`ck_summary_summaries_success_has_facts` 阻止空事实 `SUCCESS`。

**根因：** 数据库约束掩盖了应用层检查是否存在。

**修复：** 增加测试与说明，区分两层职责：service 校验负责生成清晰的
`FAILED` 状态和原因；数据库约束负责最后的数据完整性防线。

**经验：**
测试要验证错误由哪一层拦截，不只是验证最终失败；通过变异测试证明每层检查的作用。

### 3.5 A1 抽取结构不足以支持 A2 冲突检测（A2 设计阶段）

**问题：** A1
每个标签只保留第一个值。例如"工资7000元"和"工资7500元"，后者可能只增加来源
ID，数值本身丢失，A2 无法比较。A1 触发词也不包含"合同开始时间"。

**修复：** A2 新建只读事实索引
`app/services/case_analysis/fact_collector.py`，实现
`normalize`、`fingerprint`、`kind_of` 等能力；没有修改 A1
`fact_extractor.py`，`SUMMARY_VERSION` 保持 `8-A1`。

**经验：**
不可默认上游输出契约满足下游需求。用真实输入运行上游，核验多值、来源和字段是否完整；修改契约前先评估版本兼容。

### 3.6 时间线检测读取不存在的字段（A2）

**问题：** `detect_timeline_alerts` 读取 `item["time_display"]`，但
`build_timeline()` 没有该字段，实际数据在
`time_range.display`；无日期事件的显示文本还可能是"时间未知"。

**后果：** 可能把所有事件误报为"未填写日期"。

**修复：** 改用结构化字段 `time_range.precision == "unknown"`。

**经验：** 以真实 schema
和运行时结果为准；程序逻辑依赖结构化字段，不依赖展示文案。

### 3.7 来源 ID 丢失来源类型（A2）

**问题：** `subject_ids` 只存裸
UUID，序列化时无法判断它指向证据还是事件，可能产生错误链接。

**修复：** 使用 `{kind, id}` 结构保留实体类型。

**经验：** 多种实体共用 ID
字段时必须保留类型；测试要验证链接目标类型，而不只是 ID 存在。

### 3.8 attention 写入异常使分析结果卡在 GENERATING（A2）

**问题：** 待确认状态写入冲突可能连带回滚成功分析记录，留下永远处于
`GENERATING` 的行。

**修复：** 使用 SAVEPOINT 隔离 attention 写入，并在 service 层增加
`FAILED` 兜底。

**经验：** 明确状态机终态；次要副作用的失败不应让主流程卡在中间状态。

### 3.9 History 响应模型过宽（A2）

**问题：** history 端点使用错误响应模型；Pydantic
静默忽略额外字段，使不该返回的 `result_json` 未被及时发现。

**修复：** 使用专门的历史响应模型，并显式测试禁止返回的字段。

**经验：** 列表、历史和详情应有不同 schema；"序列化没报错"不等于 API
契约正确。

### 3.10 E2E 因宿主进程资源耗尽无法运行（A2 后续验证）

**问题：** 执行报告记录约 4,710 个僵尸进程，均为 `PPID=1`；PID 1 为
code-server（Node），没有回收孤儿进程。出现
`spawn EAGAIN`、`bash: fork: retry: Resource temporarily unavailable`、`uv_thread_create`
断言失败和终端 broker 崩溃。

**处理：** 没有修改无关的 `next.config.ts` 来迁就环境，也没有宣称 E2E
通过。明确记录 E2E 全量、A2 spec 和新增规则版本断言未验证。

**经验：**
环境阻塞不是测试通过，也不必然是代码失败。恢复干净环境后应重跑
`frontend/scripts/run-e2e.sh`。

### 3.11 分析快照与人工处理状态混在一起（A2 设计）

**问题：**
修改不可变分析结果来记录"确认/忽略"会破坏历史；每次点击都生成分析版本又会污染版本历史。

**修复：** 分为两张表： -
`case_analysis_results`：不可变、按案件版本化的分析结果。 -
`case_analysis_attentions`：跨版本持续的待确认状态，支持
`OPEN`、`CONFIRMED`、`IGNORED`。

通过 `fingerprint` 识别跨版本同一问题；`subject_ids` 保存
`{kind, id}`。`source_analysis_version="8-A2"`
表示规则版本，与案件内运行序号 `last_seen_version` 分开。

**经验：**
运行版本与规则版本是不同维度；不可变快照和可变工作流状态应分开。

## 4. Phase 8-A1 交付与状态

### 主要交付

-   Alembic migration：`e4a7b2c19d83_phase8a1_case_fact_summaries.py`
-   `app/models/fact_summary.py`
-   `app/schemas/fact_summary.py`
-   `app/services/summary/{fact_extractor,enhancer,summary_service}.py`
-   `app/api/v1/summary.py`
-   `tests/test_fact_summary.py`
-   前端 `summaryApi.ts`、案件摘要页、E2E 测试
-   更新模型导出、路由注册、类型、案件页和 docs 05/06/12/13、CHANGELOG

### 当时报告的验证结果

-   `pytest -q`：806 passed
-   `run-e2e.sh`：74 passed
-   `tsc`：通过
-   `eslint --max-warnings=0`：通过
-   前端单测：5 passed
-   `alembic check`：无漂移，head `e4a7b2c19d83`

### 已知限制

-   `MockSummaryEnhancer` 未接真实 LLM，真实模型质量尚未验证。
-   `employment_facts`
    是正则规则，覆盖入职、离职、岗位、薪资、用人单位；仅扫描证据
    title/description/proof_purpose。
-   摘要无分页和删除，按不可变设计处理。
-   pytest 使用 `create_all`，不等于执行了 Alembic
    migration；迁移需单独验证。
-   当时 E2E 未覆盖并发生成同一案件。

## 5. Phase 8-A2 交付与状态

### 主要交付

后端： - `app/services/case_analysis/fact_collector.py` -
`app/services/case_analysis/conflict_rules.py` -
`app/services/case_analysis/attention_service.py` -
`app/services/case_analysis/analysis_service.py` -
`app/api/v1/case_analysis.py`

前端： - `lib/caseAnalysisApi.ts` - `lib/types.ts` 追加类型 -
`app/cases/[id]/case-analysis/page.tsx` - 案件页"结构化分析"入口

测试： - `tests/test_case_analysis.py`：57 例 -
`e2e/case-analysis.spec.ts`：8 例（早期完成报告）

### 规则和数据边界

-   分析类型：`CONFLICT_DETECTION`、`EVIDENCE_COMPLETENESS`、`TIMELINE_ALERT`。
-   只描述事实差异，不判断谁对谁错，不输出违法、赔偿、责任归属或胜诉概率结论。
-   归一化值用于比较，展示保留原文。
-   分析结果存入 `case_analysis_results`，版本化且不可变。
-   待确认状态存入 `case_analysis_attentions`，跨版本持续。
-   不写入或修改 Evidence、Event、File、Timeline、Fact Summary
    等事实数据。
-   `source_analysis_version` 记录规则版本 `"8-A2"`。

### 报告中的验证状态

早期报告： - `pytest -q`：864 passed - `run-e2e.sh`：82 passed -
`tsc --noEmit`、`eslint --max-warnings=0`：通过 - 前端单测：5 passed -
`alembic check`：无漂移

增加 `source_analysis_version` 后的报告： - `pytest -q`：866 passed -
migration upgrade → downgrade → upgrade：exit 0 / 0 / 0 -
`information_schema` 新列核验成功 - `pg_constraint` 核验两张表共 11
条约束 - `alembic check` 无漂移；head `b7c4d2e85f19` -
`tsc --noEmit`、`eslint . --max-warnings=0` 通过 - 前端单测 5 pass -
**E2E 全量和 A2 spec 当轮未运行**，环境阻塞；此前 82 passed
是加字段前的结果，不能代表最新代码已完成 E2E 回归。

## 6. Phase 8-A3 设计现状

**A3 尚未编码。**
设计目标是证据缺口分析/材料完善建议。以下是方案内容，不是已经实现的功能。

### 6.1 核心原则

-   A2 检测材料之间的矛盾；A3 检测当前材料中没有找到预期类型支持的情况。
-   每条缺口必须表述为"在当前案件材料中未发现......"，不能说成"事实不存在"或"公司没有......"。
-   只能针对案件中已经出现的事实提问；案件从未出现某事实时，不凭空要求相关材料。
-   使用确定性规则，不调用 AI。
-   A1/A2 只读复用，不修改其代码与数据契约。

### 6.2 拟定数据模型

新增 `case_evidence_gap_results`，包含 `id`、`case_id`、案件内递增的
`version`、`status`（`GENERATING/SUCCESS/FAILED`）、`gap_json`、`error_type`、固定文案
`error_message`、`created_at`、`created_by`。设置版本唯一、版本正数、成功结果必须含
`missing_items` 键等约束。

`missing_items=[]` 是合法 SUCCESS，表示检查后没有发现缺口；空案件返回
409，不建行。结果按版本不可变。

每条缺口保留五个核心字段： - `title` - `description` -
`related_fact_ids` - `suggested_evidence_types` - `priority`

另建议补充： - `code`：稳定机器码 - `gap_id`：跨版本指纹 -
`sources`：带类型的来源及摘录 -
`check_basis`：搜索类型和检查过的材料/事件数量，便于审计

### 6.3 拟定规则与映射

规则： -
`FACT_NO_EXPECTED_TYPE_SOURCE`：事实存在，但没有期望类型证据支持。 -
`FACT_SINGLE_SOURCE`：只有一项证据来源，未发现独立来源。 -
`FACT_SOURCE_CONFLICT_OPEN`：A2 存在未处理的来源差异。 -
`EVENT_NO_EVIDENCE`：已确认事件没有关联证据。 -
`EVENT_UNDATED_NO_ANCHOR`：事件无日期且无证据可确定时间。

期望证据类型映射必须覆盖 A2 `VALUE_RULES` 全部六类：

  事实标签       期望类型
  -------------- ------------------------------------------------------
  入职时间       `labor_contract`、`work_record`、`attendance_record`
  合同开始时间   `labor_contract`
  离职时间       `labor_contract`、`company_notice`、`chat_record`
  薪资           `labor_contract`、`salary_record`、`bank_record`
  岗位           `labor_contract`、`work_record`
  用人单位       `labor_contract`、`company_registration`

A3 必须处理 text 类型的岗位、用人单位事实；不能照搬 A2
冲突检测的可比较类型过滤规则。

### 6.4 拟定措辞闸门

1.  只描述材料搜索结果，不描述现实世界的绝对事实。
2.  不施加义务，避免"必须""应当""需提供""否则""法定义务""举证责任"等词。
3.  计划新增 `assert_no_obligation()`，与 `assert_neutral`
    分开，避免改变 A1/A2 行为。
4.  闸门在 service 层对最终输出执行：中性校验 → 无义务措辞校验 →
    来源可追溯校验 → schema 校验。
5.  每条缺口必须有来源，建议类型必须属于 `EvidenceType` 封闭枚举。

### 6.5 API 与页面方案

拟定 API： - `POST /cases/{id}/evidence-gaps` -
`GET /cases/{id}/evidence-gaps` -
`GET /cases/{id}/evidence-gaps/history`

暂定独立页面
`app/cases/[id]/evidence-gaps/page.tsx`，案件页增加"材料缺口"入口。页面显示标题、描述、相关事实、来源类型、建议类型和搜索依据。文案避免"必须补齐""立即上传"等强制表达。

### 6.6 仍待用户确认的五项决策

1.  A3 是否需要闭环状态？设计者倾向 v1 不做，补材料后重跑即可。
2.  `EVENT_NO_EVIDENCE` 是否与 A2 `EVIDENCE_NO_LINKED_EVENT`
    重复？设计者倾向 A3 跳过，避免两个面板重复。
3.  独立页面还是 A2 第四个 tab？设计者倾向独立页面，保持 A2 页面冻结。
4.  `FACT_SINGLE_SOURCE` 是否算缺口？设计者倾向作为 INFO
    提示，但它更像"单一来源/脆弱性"。
5.  `assert_no_obligation` 使用独立词表还是并入
    `assert_neutral`？设计者倾向独立，避免悄悄改变 A1/A2 行为。

### 6.7 A3 开始编码前的核验

-   先确认上述五项决定。
-   只读核验真实 `EvidenceType`、A2 `VALUE_RULES`、`collect_fact_index`
    返回结构、`build_timeline` 结构、A2 attention 查询方式。
-   每条规则写触发/不触发用例。
-   对 `assert_no_obligation`
    做变异测试，证明每个禁用规则确实能被测试抓到。
-   明确空案件、空结果、失败状态、权限、并发生成、版本递增和不可变性。
-   未确认前不编码，不改 A1/A2。

## 7. 标准开发步骤

每个新阶段都按以下顺序执行：

1.  检查 Git 工作区、分支、未提交变更和迁移 head。
2.  阅读 PRD、功能规格、架构、数据库、API、测试计划与 AI 编码规则。
3.  检查实际模型、字段、枚举、函数签名、服务返回结构、路由和权限。
4.  先交设计稿：文件清单、schema、API、事务、失败路径、测试矩阵、禁改范围。
5.  用实际代码运行关键样例验证设计前提。
6.  把未决问题列出来，等待用户确认。
7.  按依赖实现：migration → model → schema → 规则 → service → API → 前端
    → 测试/文档。
8.  每层结束先跑相关测试。
9.  最后跑全量验证并检查 diff。
10. 更新数据库/API/测试计划/开发计划/CHANGELOG。
11. 汇报改动、测试结果、未运行项目、限制和下一阶段前置条件。
12. 未获授权不提交 Git。

## 8. 测试与验收清单

-   [ ] `pytest -q`
-   [ ] `frontend/scripts/run-e2e.sh` 或项目指定 E2E 命令
-   [ ] `tsc --noEmit`
-   [ ] `eslint --max-warnings=0`
-   [ ] 前端单测
-   [ ] `alembic check`
-   [ ] 有迁移时执行 upgrade → downgrade → upgrade
-   [ ] 核验 `alembic heads` 和数据库约束
-   [ ] `git diff --check`
-   [ ] 禁改模块 `git diff` 为空
-   [ ] 文档、CHANGELOG、API 文档已更新
-   [ ] 未运行检查有原因和补跑计划
-   [ ] 已知限制明确记录

### 环境故障的报告标准

测试未运行时写"未运行/环境阻塞"，不要写"通过"。记录原始报错、受影响检查、最后一次成功检查；不要修改无关业务配置来掩盖环境问题。环境恢复后补跑完整回归。

## 9. AI 编程工具提示模板

### 设计阶段（只读）

> 本轮只做只读核验和设计，不修改代码。检查真实仓库、模型、schema、API、服务、迁移和测试；用运行时样例验证关键假设；列出文件改动、数据库/API契约、失败行为、权限和事务边界、测试矩阵、禁改范围与待决策问题。结束时明确声明未修改任何代码。未获确认前不得编码。

### 实现阶段（确认后）

> 按已确认设计分层实现，不扩大范围。每层完成后运行相关测试；所有关键约束必须在
> service 层对最终产物执行；不得修改冻结模块；为新增
> API、数据库约束、状态转换和用户文案添加测试。最后运行后端、前端、E2E、迁移与
> diff 检查。不自动提交
> Git。报告改动文件、测试数字、未运行项、已知限制和下一阶段前置条件。

### 环境故障阶段

> 区分代码缺陷与宿主环境故障，记录错误、影响范围和最后一次成功检查。不要用修改无关业务配置来伪造测试通过。能安全运行的检查继续执行；不能运行的明确标记为阻塞，并列出环境恢复后需要执行的命令。

## 10. 下一步建议

1.  在干净或已恢复的环境中补跑 A2 E2E 全量回归，尤其是
    `source_analysis_version` 新增后的测试。
2.  确认 A3 的五项待决策问题。
3.  让 AI 对 A3
    依赖的真实代码做只读核验，避免设计建立在假字段或错误返回结构上。
4.  用户确认设计后再实现 A3。
5.  完成后执行全量测试、迁移往返、diff 范围核验并更新文档。

## 11. 后续问题记录模板

每次遇到问题，按以下结构写入项目文档：

-   **现象：** 实际发生了什么。
-   **复现：** 输入、命令或步骤。
-   **根因：** 哪个假设、数据契约或边界不正确。
-   **修复：** 修改哪一层，为什么在该层修。
-   **回归测试：** 新增哪些测试。
-   **变异测试：** 如何证明检查不能被绕过。
-   **影响范围：** 数据库/API/历史数据/其他阶段是否受影响。
-   **验证状态：** 通过、失败、未运行或环境阻塞。
-   **遗留限制：** 尚未覆盖的情况。
-   **预防规则：** 如何避免同类问题再次出现。
