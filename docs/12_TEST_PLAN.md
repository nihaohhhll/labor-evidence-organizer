# 测试计划

## Unit

测试：
- 文件 hash
- 文件类型判断
- 证据编号
- 页码
- 日期解析
- 金额解析
- confidence threshold
- JSON schema
- 导出排序
- A3 措辞闸门：义务词 / 非中性词逐族拒绝，干净文本放行
- A3 建议证据类型必须属于 EvidenceType 封闭词表
- A3 缺口 gap_id 跨版本稳定（确定性 uuid5）
- 缺口页中文标签与检查依据文案（前端 vitest）
- 材料包状态机：仅 ARCHIVED 只读（`NOT_EDITABLE`）、发布后仍可编辑、
  有快照不可删（`HAS_SNAPSHOTS`）、空包不可快照（`EMPTY_PACKAGE`）
- 成卷导出内容组装：已删文件/无文件有摘要/来源证据已删的注记路径，
  单条失败不阻断整卷
- 快照行 → 导出表格映射、完整性附录 stale 判定（草稿晚于分析）
- 下载文件名（`材料包-{名称}.{fmt}`，RFC 5987 编码；ASCII 回退合理非空、
  无 `"`/`;`/`/`/CRLF/穿越形态，头值可 latin-1 编码）
- 前端 `parseDownloadFilename`：`filename*` 优先、损坏/缺头回退、trim
- 导出失败路径：`RENDER_FAILED` 留 FAILED 行、下载 `EXPORT_NOT_FOUND`/409
  `EXPORT_NOT_READY`/410 `EXPORT_MISSING`
- 未传 `snapshot_version` → 绑定最新快照而非草稿（草稿后续修改不泄漏）

## Integration

测试：
上传 → DB
上传 → AI job
AI → Evidence
Evidence → Event
Evidence → Export
Evidence/Event → 缺口分析（A3 规则触发与不触发）
材料包 → 保存草稿 → 快照 → 成卷导出（PDF/DOCX）→ 鉴权下载
（含下载异常模式：未完成/文件缺失/不存在与渲染失败落库）

## E2E

Scenario 1：
创建案件 → 上传合同 → AI解析 → 修改 → 确认 → 导出。

Scenario 2：
批量上传 20 张聊天截图 → 解析 → 时间轴 → 证据目录。

Scenario 3：
AI 失败 → retry → 成功。

Scenario 4：
用户修改 AI 日期 → 再次 AI 分析 → 用户修改必须得到保护。

Scenario 5：
User A 尝试访问 User B 的案件 → 403/404。

Scenario 6（A3 材料缺口）：
专项案件（仅聊天记录 + 事实标签）→ 缺口分析 → 触发
FACT_NO_EXPECTED_TYPE_SOURCE（含来源与合法类型词表）→
latest/history 契约 → 越权 404。（由 scripts/e2e-smoke.sh 执行）

Scenario 7（9-C 材料包 UI，Playwright）：
由 `scripts/e2e-ui.sh` 驱动 `frontend/e2e/phase9c-ui.spec.ts`，12 个场景：
1. 空列表 → 新建材料包 → 编辑页打开（DRAFT 控件齐全）；
2. 勾选证据 → 保存草稿 → 创建快照；
3. 发布 = 纯状态标记，发布后仍可继续编辑；
4. 草稿比最新快照新时出现分歧提醒；
5. 归档 → 只读 UI + 后端统一 409 `NOT_EDITABLE`；
6. 材料包导出页：生成 PDF 卷宗并带鉴权下载（含保存名断言）；
7. 完整性附录开关：无 A3 结果禁用，分析后可用；
8. 无快照时导出页给出创建快照引导；
9. 案件导出中心下载携带鉴权（401 裸链接修复）；
10. 材料包列表按 limit=100 拉取 + 超限提示（20 条静默截断修复）；
11. 草稿删除必须 confirm：取消保留、确认删除；
12. 下载文件名兼容：英文/空格/特殊字符名（响应头回退 + `a.download` 赋值）。
注意：登录/注册有固定窗口限流，全套仅注册 1 个共享账号并经
`addInitScript` 注入 token，不走 UI 登录。headless Chromium 丢弃非
ASCII `a.download` 值，中文保存名用页面内锚点拦截验证（见 README 环境限制）。

## AI Evaluation Dataset

建立固定测试数据集：
- 清晰截图
- 模糊截图
- 长聊天截图
- 多页 PDF
- 表格
- 金额
- 日期
- 相似人物名
- 多公司名称
- OCR 错误样本

每次修改 prompt/model 必须跑 evaluation。

## Acceptance

MVP 至少：
- 90%+ 测试样本能够正确分类；
- 日期/金额等结构化字段不得出现静默错误；
- 所有低置信度结果进入 review；
- 原始文件 100% 可追溯。
