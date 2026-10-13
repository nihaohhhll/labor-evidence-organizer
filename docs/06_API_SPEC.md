# API Specification

Base URL: `/api/v1`

## Cases

POST /cases
GET /cases
GET /cases/{id}
PATCH /cases/{id}
DELETE /cases/{id}

## Files

POST /cases/{case_id}/files
GET /cases/{case_id}/files
GET /files/{id}
DELETE /files/{id}
POST /files/{id}/retry

## Analysis

POST /files/{id}/analyze
GET /files/{id}/analysis

## Evidence

GET /cases/{case_id}/evidence
POST /cases/{case_id}/evidence
GET /evidence/{id}
PATCH /evidence/{id}
DELETE /evidence/{id}
POST /evidence/{id}/reanalyze
POST /evidence/{id}/confirm

## Events

GET /cases/{case_id}/events
POST /cases/{case_id}/events
PATCH /events/{id}
DELETE /events/{id}

## Review

GET /cases/{case_id}/review-items
PATCH /review-items/{id}
POST /review-items/{id}/confirm

## Export

POST /cases/{case_id}/exports
GET /exports/{id}
GET /exports/{id}/download

- 材料包导出（绑定 `package_id`）下载文件名为 `材料包-{名称}.{pdf|docx}`，
  中文经 RFC 5987 编码（`filename*=UTF-8''…`）。`filename` 参数为 ASCII
  回退：剥离非 ASCII 与 quoted-string 元字符、`/` 与 `;` 中性化，中文名
  等回退为 `download.{fmt}` 类合理非空名，头值始终可 latin-1 编码。

## Material Packages

POST /cases/{case_id}/material-packages
GET /cases/{case_id}/material-packages?limit=&offset=
GET /material-packages/{id}
PATCH /material-packages/{id}
DELETE /material-packages/{id}
GET /material-packages/{id}/items
PUT /material-packages/{id}/items
GET /material-packages/{id}/snapshots
POST /material-packages/{id}/snapshots
GET /material-packages/{id}/snapshots/{version}
POST /material-packages/{id}/exports
GET /material-packages/{id}/exports

可选证据列表复用 `GET /cases/{case_id}/evidence`。

规则：
- 状态机 `DRAFT → PUBLISHED → ARCHIVED`；发布是纯状态标记，发布后仍可编辑；
  仅 ARCHIVED 只读（编辑 → 409 `NOT_EDITABLE`）；删除仅限 DRAFT 且
  `snapshot_count == 0`（有快照 → 409 `HAS_SNAPSHOTS`）。
- 保存带 `draft_version` 乐观锁，冲突 → 409 `VERSION_CONFLICT`；
  空包创建快照 → 409 `EMPTY_PACKAGE`；快照内容不可变。
- 导出按快照渲染（不传 `snapshot_version` 时取最新）；未创建任何快照 →
  409 `SNAPSHOT_REQUIRED`；请求体
  `{format: "pdf"|"docx", snapshot_version?, include_gap_appendix}`，
  非法格式 → 422 `UNSUPPORTED_FORMAT`；完整性附录需要已有 A3 成功结果，
  否则 → 409 `GAP_APPENDIX_UNAVAILABLE`；导出记录绑定
  `snapshot_id/snapshot_version`，进审计 `EXPORT_CREATED`。
- `GET /material-packages/{id}/exports` 返回该包的历史导出记录
  （`package_id/snapshot_id/snapshot_version/include_gap_appendix/gap_result_id`）。
- 越权/跨案件访问一律 404；跨案件证据引用与不存在的 ID 返回同一错误码（防探测）。

## Evidence Gaps (A3)

POST /cases/{case_id}/evidence-gaps
GET /cases/{case_id}/evidence-gaps
GET /cases/{case_id}/evidence-gaps/history?limit=&offset=

规则：
- 空案件（无证据且无事件）→ 400 `GAP_ANALYSIS_FAILED`，不建行。
- GET latest 无记录 → 404 `GAP_NOT_FOUND`。
- 所有端点按案件归属校验，越权 → 404（不泄露资源存在性）。
- 结果按版本不可变；`version` 从 1 递增；`gap_json.missing_items`
  恒为数组（`[]` 表示检查后未发现缺口）。
- `gap_id` 为确定性 uuid5（跨版本指纹），同一缺口在重跑后保持不变。

## API Rules

- 所有 endpoint 必须进行用户权限校验。
- 使用 Pydantic schema。
- 跨源：注册 CORSMiddleware，`cors_allow_origins` 白名单（默认
  `localhost:3000`/`127.0.0.1:3000`），`allow_credentials=false`
  （JWT 走 `Authorization` 头，不用 Cookie）；暴露响应头仅
  `Content-Disposition`、`X-Request-ID`。
- 错误格式统一：
{
  "error": {
    "code": "...",
    "message": "...",
    "request_id": "..."
  }
}
- 不向客户端返回内部异常堆栈。
