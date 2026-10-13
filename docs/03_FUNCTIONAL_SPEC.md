# 功能规格

## 1. 案件首页

展示：
- 案件名称
- 文件总数
- 已解析
- 待确认
- 已确认
- 时间轴事件数量
- 导出状态

## 2. 文件上传

允许：
- 拖拽；
- 文件选择；
- 批量上传。

限制：
- 文件类型白名单；
- 文件大小限制；
- 病毒/恶意文件基础检查；
- 重复文件检测（SHA-256）。

## 3. 文件处理状态

状态：
UPLOADED
QUEUED
PROCESSING
REVIEW_REQUIRED
COMPLETED
FAILED

## 4. AI 分类

初始分类：
- labor_contract
- company_notice
- chat_record
- bank_statement
- salary_statement
- attendance_record
- social_insurance
- identity_document
- company_registration
- work_record
- other

分类只是建议，用户可以修改。

## 5. Evidence

字段：
- evidence_number
- title
- category
- event_date
- summary
- proof_purpose
- confidence
- review_status

## 6. 时间轴

每个 Event：
- 日期
- 时间（可空）
- 标题
- 描述
- 来源证据
- confidence
- review_status

用户可以：
- 修改；
- 删除；
- 合并；
- 新增；
- 调整日期。

## 7. 证明目的

AI 只能生成事实性建议。

推荐格式：
“用于证明……这一事实。”

避免默认生成：
“证明公司违法……”
“证明公司应当……”
“证明仲裁请求成立……”

除非用户主动输入并确认。

## 8. 导出

证据目录：
| 编号 | 证据名称 | 形成时间 | 证明目的 |

时间轴：
| 日期 | 事件 | 来源证据 |

证据正文：
- 编号；
- 标题；
- 原始页面；
- 页码。

