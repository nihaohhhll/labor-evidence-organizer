# 19 · 劳动仲裁案件工作台改造 —— 阶段一审查与实施计划

> 审查日期：2026-10-15。基于 master@3f4fcac（SQLite/PG 双库 275 测试全过、
> 前端 tsc+vitest 23 全过、绿色版/安装版已交付）。

## 1. 现有功能盘点（均已验证，不重写）

### 1.1 后端（FastAPI + SQLAlchemy，10 组路由，60+ 端点）

| 模块 | 能力 | 状态 |
| --- | --- | --- |
| 认证 | register/login/me，JWT，全路由所有权校验 | ✅ 完整 |
| 案件 | 列表/详情/改名/叙述/删除，file/evidence/event 计数 | ✅ 完整 |
| 文件 | 多类型上传、状态机 UPLOADED→PROCESSING→READY/FAILED、重试、blob 预览、删除、状态统计 | ✅ 完整 |
| AI 流水线 | mock/OpenAI provider、DocumentAnalysis（原始 JSON+模型+prompt 版本）、按字段 ReviewItem、重分析不覆盖用户已改字段（user_edited_fields） | ✅ 完整 |
| 证据 | 自动建议入库（案件内唯一编号）、列表/详情/修改（记录人工编辑字段）、确认/拒绝、重分析、删除、摘录+source_ref 溯源 | ✅ 完整 |
| 时间轴 | precision（day/month/unknown）、从已确认证据构建事件、CRUD、合并、证据关联 | ✅ 完整 |
| 材料包 | 草稿编排（展示编号/拟证明事项/项审核）、版本快照、快照历史、按快照导出 | ✅ 完整 |
| 导出 | 案件级 docx/pdf/zip（zip 含原件）、下载/查看/删除、审计 | ✅ 完整 |
| 材料缺口 A3 | AI 缺口分析多版本+历史 | ✅ 完整 |
| 审计 | AuditLog（action+entity+metadata，带脱敏约定）、`recent_for_case` 服务 | ✅ 服务存在，**无 API 暴露** |
| Claim 模型 | claims 表 + evidence_claims 连接表 | ⚠️ **模型存在但零路由零 UI** |

### 1.2 前端（Next.js 14 App Router，Tailwind，自研轻量设计 token）

- 路由：/login、/cases、/cases/new、/cases/[id] 及 files/review/timeline/
  evidence/evidence-gaps/export/material-packages（+new/edit/export/history）。
- 设计 token：globals.css 已有 card/btn/input/empty-state/ai-badge。
- 布局：案件侧边栏 8 平铺项 + 统一滚动容器；资料库/时间轴 sticky 头部；
  审核工作台左原始右证据双栏。
- 测试：vitest 23（纯函数）；Playwright e2e 覆盖材料包发布流。

### 1.3 基础设施

本地存储、inline job、限流、安全头、日志脱敏、PG/SQLite 双支持、
Windows 绿色版+安装版构建流水线。

## 2. 与新 IA 的差距

| 新 IA 要求 | 现状 | 差距 |
| --- | --- | --- |
| 案件首页（阶段/统计/任务/动态） | 仅叙述编辑+3 个计数 | 缺阶段计算、任务清单、最近动态、审计 API |
| 证据中心 | files/review/evidence/gaps 四页能力齐 | 缺统一导航分组与案件头 |
| 事实时间线 | 功能齐（含精度、合并、冲突来源） | 基本满足，小改文案 |
| 请求与证据关联 | **仅有 Claim 模型** | 缺路由、页面、金额/计算/事实关联 |
| 材料生成中心 | 材料包+导出齐全 | 缺统一入口与导出前检查提示 |
| 庭审准备 | 无 | 全新（清单+庭审日期+结果记录） |
| 案件归档 | 导出历史+案件删除；status PATCH 已有 | 缺归档页（归档动作/文件清单/数据管理） |
| 设置与数据管理 | 无页面 | 缺诚实的能力/限制说明页 |

## 3. 新旧映射（路由级）

| 新导航 | 既有路由 | 处置 |
| --- | --- | --- |
| 案件首页 | /cases/[id] | 重写内容，路由不变 |
| 证据中心 | /files（上传）、/review（审核）、/evidence（目录）、/evidence-gaps（缺口） | 路由全保留，导航归组 |
| 事实时间线 | /timeline | 保留，文案微调 |
| 请求与证据关联 | 无 | **新页** /claims |
| 材料生成 | /material-packages/*、/export | 保留路由，首页/导航重组入口 |
| 庭审准备 | 无 | **新页** /trial-prep |
| 案件归档 | /export + PATCH status | **新页** /archive（整合导出历史+归档+删除） |
| 设置与数据管理 | 无 | **新页** /settings |

## 4. 需要的后端改动（最小集）

### 4.1 数据库迁移（1 个 alembic 版本，全部向后兼容）

1. `claims` 扩展：`amount`（String 32，金额按用户原文存，避免浮点）、
   `calculation`（Text 计算明细）、`status`（DRAFT/CONFIRMED）、`notes`。
   理由：需求 4.4 明确要求金额与计算依据；列均可空，旧行 NULL 兼容。
2. 新连接表 `claim_events`（请求↔事实），对称于既有 evidence_claims。
3. `cases.trial_prep`（JSON 可空）：庭审日期/通知备注/清单勾选/调解裁决记录。
   理由：庭审准备 1:1 依附案件，JSON 列比新表侵入更小。
   回滚：DROP COLUMN / DROP TABLE，无数据转换。
   SQLite：便携版 create_all 自动生效；PG：alembic upgrade。

### 4.2 新端点（全部带测试）

- `GET /cases/{id}/progress`：阶段(0-7)+真实计数+任务清单+下一步动作（纯计算，无新表）。
- Claims：`GET/POST /cases/{id}/claims`、`GET/PATCH/DELETE /claims/{id}`；
  create/update 接受 `evidence_ids`/`event_ids` 维护关联。
- `GET/PATCH /cases/{id}/trial-prep`。
- `GET /cases/{id}/audit?limit=`：暴露既有 recent_for_case（metadata 已按
  安全文档约定不含敏感全文）。

### 4.3 明确不做

- 不改文件支持范围/编号语义/版本快照机制；不动材料包与导出内核；
- 不引入新大型依赖、不新增无关表；不伪造备份/加密/合规能力。

## 5. 前端改动计划

1. `components/workbench`：PageHeader、StatusBadge、StatCard、TaskList 等小原语（复用现有 token）。
2. `cases/[id]/layout.tsx`：工作台外壳——顶部案件名+状态+阶段徽章、
   分组左侧导航、移动端折叠导航；保留统一滚动容器。
3. 首页重写：阶段横幅、统计卡、待办任务（真实数据）、最近动态、
   快捷入口；叙述编辑保留。
4. 新页：/claims、/trial-prep、/archive、/settings（全部真实 API）。
5. 存量页：只改导航呈现与个别文案，不动业务交互（保护 e2e 与已验证行为）。

## 6. 阶段划分与验收

- 阶段二：框架+首页（本计划 5.1–5.3）。
- 阶段三：按 5.4 逐模块，每模块完成后跑该模块相关测试。
- 阶段四：后端 pytest（SQLite+PG）、tsc、vitest、next build、
  Playwright 材料包 e2e、开发服务器冒烟。

## 7. 风险与边界

- Playwright e2e 锚定材料包页文案——该页内部不改。
- AI 缺口/叙述/mock 数据一律真实链路，无演示假数据。
- 进度/阶段只描述整理完成度，不出现胜诉率/法律结论措辞。
