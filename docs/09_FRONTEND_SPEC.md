# 前端规格

## 页面

### /cases
案件列表

### /cases/new
创建案件

### /cases/[id]
案件 Dashboard

### /cases/[id]/files
资料库

### /cases/[id]/review
AI 审核工作台

### /cases/[id]/timeline
案件时间轴

### /cases/[id]/evidence
证据目录

### /cases/[id]/export
导出中心

## Dashboard

卡片：
- 文件数量
- 处理中
- 待确认
- 已确认
- 时间轴事件
- 证据数量

## Review Workbench

桌面端：
左侧原始文件；
右侧结构化结果。

移动端：
上下布局。

字段状态：
- AI generated
- User edited
- Confirmed
- Needs review

## UI 原则

- 简洁；
- 面向非法律专业用户；
- 避免大量法律术语；
- 所有 AI 内容有明显标识；
- 高风险/低置信度内容显著提示；
- 永远提供“查看原始材料”。

## Empty State

没有资料：
“把合同、聊天截图、工资记录等资料拖进来，AI 会先帮你整理。”

## Error State

AI 失败：
“这份资料暂时没有解析成功。原文件没有受到影响，你可以重试或手动整理。”
