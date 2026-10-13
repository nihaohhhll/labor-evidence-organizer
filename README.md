# 劳动争议证据整理器（Labor Evidence Organizer）

把合同、聊天截图、工资单、银行流水等零散材料，解析、分类、结构化成**可人工核对、可追溯、可打印**的证据包。

> 本产品只帮用户**整理材料**，不替用户作法律判断。所有 AI 输出均为建议，用户可修改；原始文件永不被改写。

规格文档见 [`docs/`](./docs/)，本仓库严格按 `docs/13_DEVELOPMENT_PLAN.md` 的 Phase 推进。

---

## 核心闭环

```
上传资料 → AI 解析 → 自动分类 → 提取事实/事件 → 证据建议
        → 人工核对 → 自动编号 → 生成时间轴 → 导出 DOCX/PDF/ZIP
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Next.js 14 + TypeScript(strict) + Tailwind CSS |
| 后端 | Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 |
| 数据库 | PostgreSQL 15 + Alembic |
| 存储 | 本地文件（开发）／ S3 兼容（生产），`Storage` 协议抽象 |
| AI / OCR | Provider 协议抽象，默认 mock（确定性、离线、不编造） |
| 文档 | python-docx、PyMuPDF、ReportLab |
| 测试 | pytest、Playwright（E2E 脚本见 `scripts/`） |

## 快速开始

### 1. 数据库

```bash
# 本项目开发环境用的是原生 PostgreSQL 15
pg_ctlcluster 15 main start
```

### 2. 后端

```bash
cp .env.example .env

cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/alembic upgrade head      # 建表
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev                            # http://127.0.0.1:3000
```

### 便捷脚本

```bash
scripts/dev-restart-backend.sh   # 重启 API
scripts/dev-restart-frontend.sh  # 重启前端
scripts/e2e-smoke.sh             # 端到端全流程验收
scripts/e2e-material-packages.sh # 材料包 14 步 HTTP 端到端
scripts/e2e-ui.sh                # Playwright UI E2E（材料包 12 场景）
```

## 架构

```
Browser → Next.js → FastAPI → PostgreSQL → Object Storage
                            ↘ Job Queue → AI/OCR Worker
```

### 五条不可妥协的架构规则（docs/04）

1. **原始文件不可变**——`LocalStorage` 写入后拒绝覆盖，任何解析/OCR/导出都产生派生数据。
2. **AI 结果是独立记录**——`document_analyses` 只追加，重新分析新建行，绝不改写历史。
3. **用户修改优先**——`evidence.user_edited_fields` 记录人工改过的字段；重新分析时这些字段被跳过。
4. **约束放在 service 层**——中性表述校验、状态机、编号分配都在 service 执行，而不是在被检查的组件内部。
5. **AI 输出可追溯**——每条结果保存 `provider / model / prompt_version / confidence`。

### 关键设计取舍

- **分类用全规则打分，不是首条命中**：`劳动合同` 是 `解除劳动合同` 的子串，顺序扫描会把解聘通知误判成合同。现在对每条规则计分，通知类关键词额外加分。
- **日期双向匹配**：触发词前后的语序都覆盖，`于2022年10月入职` 和 `入职日期：2022年10月` 都能命中。
- **`COMPLETED` 不是终态**：规格要求支持「重新分析」，所以只有 `FAILED` 需要显式重试才能再处理。
- **服务层不碰 HTTP**：service 抛 `FileServiceError`，路由用 `owned_case_or_404` 统一翻译成 404，避免越权泄露资源是否存在。
- **中文下载文件名走 RFC 5987**：HTTP 头必须是 latin-1，`Content-Disposition` 同时给 ASCII 回退值和 `filename*=UTF-8''…`。

## API 概览

Base URL `/api/v1`，共 **55 个端点**。错误响应统一为：

```json
{ "error": { "code": "CASE_NOT_FOUND", "message": "…", "request_id": "…" } }
```

| 分组 | 端点 |
| --- | --- |
| auth | `POST /auth/register`、`POST /auth/login`、`GET /auth/me` |
| cases | `POST/GET/PATCH/DELETE /cases[/{id}]` |
| files | `POST/GET /cases/{id}/files`、`GET/DELETE /files/{id}`、`POST /files/{id}/retry`、`GET /files/{id}/content` |
| analysis | `POST /files/{id}/analyze`、`GET /files/{id}/analysis`、`POST /cases/{id}/analyze` |
| evidence | `GET/POST /cases/{id}/evidence`、`GET/PATCH/DELETE /evidence/{id}`、`POST /evidence/{id}/confirm`、`POST /evidence/{id}/reanalyze` |
| review | `GET /cases/{id}/review-items`、`PATCH /review-items/{id}`、`POST /review-items/{id}/confirm`、`POST /review-items/{id}/discard` |
| timeline | `GET/POST /cases/{id}/events`、`POST /cases/{id}/events/build`、`GET/PATCH/DELETE /events/{id}`、`POST /events/merge` |
| export | `POST/GET /cases/{id}/exports`、`GET /exports/{id}`、`GET /exports/{id}/download` |
| evidence-gaps (A3) | `POST/GET /cases/{id}/evidence-gaps`、`GET /cases/{id}/evidence-gaps/history` |
| material-packages | `POST/GET /cases/{id}/material-packages`、`GET/PATCH/DELETE /material-packages/{id}`、`GET/PUT .../items`、`GET/POST .../snapshots`、`GET .../snapshots/{version}`、`POST/GET .../exports` |

## 验证状态

以下命令在本项目开发环境中**实际运行并全部通过**：

| 检查 | 结果 |
| --- | --- |
| `backend: pytest -q` | **270 passed**（0 failed，含材料包成卷导出 18 例、下载文件名头 13 例、A3 缺口分析 30 例） |
| `frontend: vitest run` | **22 passed**（含下载文件名解析 5 例；`vitest.config.ts` 限定只收 `src/**`） |
| `frontend: tsc --noEmit` | 通过（strict，含 `noUncheckedIndexedAccess`） |
| `frontend: eslint` | 通过（`src` + `e2e`，0 warning） |
| `frontend: next build` | 通过，17 个路由 |
| `alembic upgrade head → downgrade base → upgrade head` + `alembic check` | 往返通过，无 schema 漂移 |
| `scripts/e2e-smoke.sh` | 通过（真实 HTTP + 真实 PostgreSQL，含 A3 材料缺口步骤） |
| `scripts/e2e-material-packages.sh` | 通过（14 步全部真实执行，前后端同时运行时无跳过） |
| `scripts/e2e-ui.sh`（Playwright） | 通过（材料包 12 场景，含下载文件名兼容场景） |
| `scripts/e2e-real-materials.sh` | 通过（9-D 真实脱敏材料 M1-M12 矩阵 + M1 七跳可追溯链 + M8 状态机闭环 + mock OCR 空文本固化） |

### 未运行 / 环境阻塞

- **Docker Compose**：本开发环境无 Docker，`docker-compose.yml` 按规格编写但**从未执行**。数据库用原生 PostgreSQL 15 代替。
- **Playwright 覆盖范围**：仅材料包 9-C 的 12 个场景（`frontend/e2e/`）真实跑过；其余页面（登录、上传、审核、时间轴等）尚无浏览器 E2E，等价覆盖由 `scripts/e2e-smoke.sh` 通过真实 HTTP 完成，前端交互仍需人工过一遍。
- **headless Chromium 下载名限制**：Playwright 驱动的 headless Chromium 会丢弃含非 ASCII 字符的 `a.download` 值（`suggestedFilename()` 报默认 `download`，裸锚点探测亦复现）。中文保存名的浏览器侧验证改用页面内锚点拦截断言 `a.download` 赋值；真实桌面 Chrome 对非 ASCII `download` 属性值按规范使用，未在本环境验证。
- **真实 AI / OCR Provider**：只实现了确定性的 mock provider。生产接入 OpenAI/Anthropic/PaddleOCR 时需补 provider 实现并跑 `docs/12` 的 AI evaluation 数据集。
- **`STORAGE_BACKEND=s3`**：代码就绪但未连接真实 S3 验证。

## 已知限制

- 异步任务当前是 `JOB_BACKEND=inline`（请求内同步执行）。生产应切到 Redis + RQ，`docker-compose.yml` 已备好 worker。
- 图片 OCR 在 mock provider 下返回空文本，因此图片会被分类为 `other` 且置信度低——这是诚实行为，不是缺陷。
- 时间轴合并后，被合并事件的 ID 保留在 `merged_into_id`，但 UI 未提供「撤销合并」。
- 材料缺口分析（A3）是 v1：确定性规则、无闭环状态；空案件分析返回 400 且不建结果行；`FAILED` 状态未落库（数据库故障时直接 500，无兜底行）。

## 目录结构

```
backend/
  app/
    ai/          provider 协议、确定性规则、mock 实现、注册表
    files/       上传校验（扩展名 + MIME + magic bytes）
    parsers/     PDF / DOCX / TXT / 图片 解析
    routes/      HTTP 层，只做参数与权限翻译
    services/    业务规则（编号、状态机、版本保护、导出渲染）
    models/      SQLAlchemy 模型
  alembic/       迁移
  tests/         270 个测试
frontend/
  src/app/       Next.js App Router 页面
  src/lib/       类型定义 + 统一 API 客户端
  e2e/           Playwright UI 场景（材料包 9-C）
docs/            18 份规格文档 + 工程复盘
scripts/         开发与验收脚本
```
