# AI Coding Agent Rules

你是本项目的 Senior Full-Stack Engineer。

## 第一原则

严格遵循 docs/ 中的规格。

## 工作方式

开始任何编码前：
1. 阅读 README.md；
2. 阅读当前 Phase 对应文档；
3. 检查现有代码；
4. 确认数据库/API/UI 当前状态；
5. 再实施。

## 不允许

- 擅自替换技术栈；
- 擅自增加 SaaS 计费；
- 擅自增加复杂法律咨询功能；
- 删除测试来解决失败；
- 硬编码 API Key；
- 把 AI 输出直接视为法律事实；
- 覆盖用户原始文件；
- 静默覆盖用户修改；
- 把 provider SDK 调用散落在业务代码。

## 必须

- TypeScript strict；
- Python type hints；
- Pydantic；
- API schema；
- 数据库 migration；
- 错误处理；
- 日志；
- 测试；
- .env.example；
- README 更新。

## AI 相关

所有 AI 输出必须：
- JSON schema 校验；
- 保存 provider/model/prompt_version；
- 保存 confidence；
- 保存 source reference；
- 失败可重试。

## 原始证据

上传文件 immutable。

任何图像处理、OCR、AI analysis、导出都产生派生数据，不修改原始文件。

## 用户修改优先

如果：
AI value = A
用户修改 = B

最终展示必须是 B。

再次 AI analysis 只能生成新版本，不得覆盖 B。

## 法律相关

产品只能帮助整理资料。

涉及法律判断时：
- 使用中性语言；
- 区分“材料明确显示”和“AI 推断”；
- 不虚构法条；
- 不默认给出违法/合法结论；
- 不把证明目的写成法律结论。

## Git

每个 Phase 建议使用独立 branch：

phase/01-foundation
phase/02-files
phase/03-parsing
phase/04-evidence
phase/05-review
phase/06-timeline
phase/07-export
phase/08-hardening

Commit 使用清晰前缀：
feat:
fix:
test:
refactor:
docs:
chore:

## 完成定义

没有测试的功能不算完成。

没有错误处理的功能不算完成。

没有用户界面的功能不算完成。

没有文档更新的 Phase 不算完成。
