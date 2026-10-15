# 20 · 劳动仲裁案件工作台改造 —— 最终交付报告

> 交付日期：2026-10-15。基于 docs/19 的阶段一~四执行完毕。
> 代码状态：**已实现、全量验证通过、尚未 git commit**（改动见 §1）。

## 1. 改动清单

### 1.1 后端（11 个既有文件修改 + 4 个新文件）

| 文件 | 内容 |
| --- | --- |
| `backend/app/services/workbench.py`（新增） | `derive_progress` 纯函数：阶段(0-7)+12 项任务清单+下一步动作；`trial_prep_complete`（6 项清单） |
| `backend/app/routes/cases.py` | 新端点 `GET /cases/{id}/progress`、`GET/PATCH /cases/{id}/trial-prep`、`GET /cases/{id}/audit` |
| `backend/app/routes/claims.py`（新增） | Claims CRUD：`GET/POST /cases/{id}/claims`、`GET/PATCH/DELETE /claims/{id}`；create/update 接受 `evidence_ids`/`event_ids` 维护关联，跨案件链接拒绝 |
| `backend/app/models/claim.py` | claims 扩展 `amount`（原文金额字符串）/`calculation`/`status`(DRAFT/CONFIRMED)/`notes`；新增 `claim_events` 连接表 |
| `backend/app/models/case.py` | `cases.trial_prep` JSON 列（庭审日期/备注/清单/调裁记录） |
| `backend/app/schemas.py` | Progress/TrialPrep/AuditLog/Claim 全套出入参模型 |
| `backend/app/services/audit.py` | `recent_for_case` 排序/limit 完善，供 API 暴露 |
| `backend/alembic/versions/c8f3a29d1b47_claims_and_trial_prep.py`（新增） | 单版本迁移：claims 扩展 + claim_events + cases.trial_prep，全部可空向后兼容，回滚即 DROP |
| `backend/tests/test_workbench.py`（新增） | 14 个测试：claims CRUD/关联/越权、progress 阶段推进、trial-prep 往返与越权、audit 列表与越权 |

### 1.2 前端（4 个页面 + 2 个组件文件 + 布局/首页重写）

| 文件 | 内容 |
| --- | --- |
| `frontend/src/components/workbench.tsx`（新增） | PageHeader / StageBadge / StatusBadge / StatCard / TaskList 小原语（复用既有 token） |
| `cases/[id]/layout.tsx` | 工作台外壳：顶部案件名+状态+阶段徽章，三组导航（工作台 / 输出与开庭 / 其他），移动端折叠为纵向 |
| `cases/[id]/page.tsx` | 首页重写：阶段横幅、6 张统计卡（全部可点击跳转）、真实待办任务、最近处理记录（audit）、叙述编辑保留 |
| `cases/[id]/claims/page.tsx`（新增） | 请求与证据关联：金额/计算依据/状态、证据与事件关联 |
| `cases/[id]/trial-prep/page.tsx`（新增） | 庭审准备：庭审日期、6 项清单、调解/裁决记录 |
| `cases/[id]/archive/page.tsx`（新增） | 案件归档：导出历史入口、状态流转、数据管理说明 |
| `cases/[id]/settings/page.tsx`（新增） | 设置与数据管理：诚实的能力/限制说明 + 退出登录 |
| `lib/api.ts` / `lib/types.ts` | 新端点封装与类型（+42/+54 行） |

存量页（files/review/evidence/gaps/timeline/material-packages/export）**内部未动**，
导航与文案由新 layout 统一承担，保护已验证的 e2e 行为。

### 1.3 文档

- `docs/19_WORKBENCH_PHASE1_AUDIT.md`：阶段一盘点与实施计划（opencode 产出）。
- `docs/20_WORKBENCH_FINAL_REPORT.md`：本报告。
- `CHANGELOG.md`：新增「工作台改造」条目。

## 2. 新旧路由映射（与 docs/19 §3 一致，全部落地）

| 新导航 | 路由 | 状态 |
| --- | --- | --- |
| 案件首页 | `/cases/[id]` | ✅ 重写（阶段/统计/任务/动态） |
| 证据中心 | `/files` `/review` `/evidence` `/evidence-gaps` | ✅ 保留，导航归组 |
| 事实时间线 | `/timeline` | ✅ 保留（导航文案改为「事实时间线」） |
| 请求与证据关联 | `/claims` | ✅ 新页 + 后端 CRUD |
| 材料生成 | `/material-packages/*` `/export` | ✅ 保留，首页统计卡与任务提供统一入口 |
| 庭审准备 | `/trial-prep` | ✅ 新页 + `GET/PATCH` 端点 |
| 案件归档 | `/archive` | ✅ 新页（整合导出历史+归档） |
| 设置与数据管理 | `/settings` | ✅ 新页 |

## 3. 验收结果（阶段四，全部本机实跑）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 后端 pytest（PG 15） | `backend/.venv/bin/python -m pytest` | ✅ **289 passed**（基线 275 + 新增 14），188s |
| 后端 pytest（SQLite） | `TEST_DATABASE_URL=sqlite:////tmp/... pytest` | ✅ **289 passed**，86s |
| Alembic | `alembic upgrade head` 至 c8f3a29d1b47 | ✅ 6 个版本链式升级成功 |
| 前端类型检查 | `tsc --noEmit` | ✅ 0 错误 |
| 前端 Lint | `eslint --max-warnings=0 .` | ✅ 0 警告 |
| 前端单测 | `vitest run` | ✅ 23 passed（4 文件） |
| 生产构建 | `next build` | ✅ 通过，含 4 个新路由（claims/trial-prep/archive/settings） |
| 材料包 HTTP e2e | `scripts/e2e-material-packages.sh` | ✅ 14 步全过（快照/409 冲突/越权 404/来源异常标注） |
| Playwright UI e2e | `scripts/e2e-ui.sh` | ✅ **12/12 passed**（45.9s） |
| API 冒烟（真实链路） | register→case→progress→claim→trial-prep→audit | ✅ 全部 200，audit 正确记录 `claim.created`/`trial_prep.updated` |
| 页面冒烟 :3000 | 12 个子路由 | ✅ 全 200（案件根 308 为尾斜杠重定向，正常） |
| 用户链路 :7860 | `/proxy/3001/*`、`/proxy/8000/healthz`、静态 chunk | ✅ 200 |

冒烟账号：`smoke-e2e@example.com`（案件「冒烟测试案件」，PG `labor_evidence` 库）。

## 4. 环境事件与处置（2026-10-15 容器镜像重建）

镜像于 07:54 重建，导致以下丢失，已全部重建：

| 丢失项 | 处置 |
| --- | --- |
| `backend/.venv`、`frontend/node_modules`（startup.sh 备份排除项） | ✅ 重装（venv + `npm ci`） |
| PostgreSQL 15 与**旧开发库数据**（容器层，无 dump 备份） | ✅ 重装 PG、建 `labor_evidence`/`labor_evidence_test`、alembic 升级；**旧案件数据不可恢复**（见 §6） |
| Playwright 浏览器（`~/.cache` 被备份排除） | ✅ `npx playwright install chromium` |

## 5. 遗留观察（不阻塞交付）

- **任务清单的「空态即完成」语义**：全新案件上「生成证据建议 / 核对时间线 / 关联证据」
  等显示为已完成（`done = 当前无可做之事`）。这是 `derive_progress` 的既定设计并有
  测试锁定（阶段 0 + 下一步动作 `/files` 仍能正确引导）；若希望空案件上这些项显示为
  未完成，需要连同 `test_progress_empty_case` 一起改语义——属产品决策，未擅动。
- `scripts/start-frontend-proxy.sh` 冒烟里 `--write-out '%{url_path}'` 在本机 curl 版本
  不受支持（仅影响该行日志输出，不影响代理功能）。
- Docker/compose 相关能力仍为静态评审（本环境无 Docker），与 9-D 结论一致。

## 6. 数据说明（重要）

- 旧容器的开发数据库（张伟案等真实案件数据）存于容器层 PG 数据目录，
  **镜像重建后未进备份、已丢失**；`backend/var/storage/` 下的证据原件文件仍在，
  但数据库行已不存在（孤儿文件）。
- 持久化备份（Dataset tar）只覆盖 `/root`，且排除 `*/.venv`、`*/node_modules`、缓存。
  如需跨重建保留开发库，应把 PG 数据目录放到 `/root` 下或纳入 `scripts/backup.sh` 轮回。

## 7. 待办（移交）

1. **git commit**（21 个改动/新文件未提交；建议按阶段拆分或单提交「工作台改造」）。
2. 决定 §5 的任务空态语义是否调整。
3. 若需真实数据：从旧备份恢复不可行，需重新录入或接入 `scripts/backup.sh` 定期备份。
