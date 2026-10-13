# 劳动争议证据整理器（Labor Evidence Organizer）

## 1. 项目定位

劳动争议证据整理器是一款面向普通劳动者、法律服务从业者及其他证据整理场景的 Web 应用。

核心价值：

> 将用户手中的截图、PDF、合同、工资单、银行流水、聊天记录等杂乱资料，自动解析、分类、结构化，并生成可人工核对的证据包。

产品不是“AI 律师”，也不替用户作最终法律判断。

核心闭环：

上传资料 → AI 解析 → 自动分类 → 提取事实/事件 → 生成证据建议 → 人工核对 → 自动编号 → Word/PDF 导出。

## 2. MVP 范围

### 支持
- PNG/JPG/JPEG
- PDF
- DOCX
- TXT
- 多文件批量上传
- OCR / 文档解析
- 文件分类
- 日期/金额/人物/组织/事件提取
- 证据目录
- 案件时间轴
- 证明目的建议
- 人工审核
- Word/PDF 导出
- 原始文件与 AI 结果分离保存

### 暂不支持
- 自动提交仲裁/诉讼
- 自动联系公司、法院、仲裁委
- 自动判断用户是否“违法”
- 自动生成具有法律效力的法律意见
- 自动替用户作出诉求选择
- 音频/视频深度分析
- 微信原始数据库导入
- 复杂团队协作
- 计费系统

## 3. 核心原则

1. 原始证据不可变。
2. AI 结果永远是建议，用户可以修改。
3. 所有 AI 生成字段必须能够追溯到原始文件。
4. 低置信度信息必须进入人工确认队列。
5. 不允许 AI 默默覆盖用户修改。
6. 所有导出文件都应注明生成时间和案件标识。
7. 法律相关文本使用中性、事实性表述，避免把推测当成事实。
8. MVP 优先保证“整理可靠”，而不是“法律分析复杂”。

## 4. 技术栈

- Frontend: Next.js + TypeScript + Tailwind CSS + shadcn/ui
- Backend: Python + FastAPI + Pydantic + SQLAlchemy
- Database: PostgreSQL
- Object Storage: 开发环境本地文件；生产环境 S3-compatible
- Async Job: MVP 可使用 Redis + Celery/RQ；也允许第一版使用数据库任务表
- AI: Provider abstraction，支持 OpenAI / Anthropic / Gemini 等
- OCR: Provider abstraction，可接 Vision LLM、PaddleOCR 或云 OCR
- Document: python-docx、PyMuPDF、ReportLab 等
- Test: Pytest + Playwright
- Deployment: Docker Compose；后续可迁移云环境

## 5. 开发原则

必须分 Phase 实现。每个 Phase：
1. 先实现；
2. 运行测试；
3. 修复错误；
4. 更新文档；
5. 再进入下一 Phase。

不得一次性生成大量未经验证的代码。

## 6. 完成标准

当以下流程能够稳定运行时，MVP 视为完成：

创建案件 → 批量上传 20+ 文件 → 自动解析 → 查看解析结果 → 修改 AI 结果 → 生成时间轴 → 生成证据目录 → 生成 Word/PDF → 下载证据包。

