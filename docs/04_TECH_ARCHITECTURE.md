# 技术架构

## 总体

Browser
  ↓
Next.js Web
  ↓ HTTP/JSON
FastAPI
  ↓
PostgreSQL
  ↓
Object Storage

异步：
FastAPI → Job Queue → AI/OCR Worker → PostgreSQL/Object Storage

## 模块

### Web
- auth
- cases
- evidence
- timeline
- review
- export

### API
- case service
- file service
- evidence service
- event service
- review service
- export service

### AI Service

统一接口：

```python
class AIProvider(Protocol):
    async def analyze_document(self, input: DocumentInput) -> DocumentAnalysis:
        ...
```

不要在业务代码中直接调用具体厂商 SDK。

### OCR

```python
class OCRProvider(Protocol):
    async def extract(self, document: DocumentInput) -> OCRResult:
        ...
```

## 可靠性

所有异步任务必须：
- 有 job_id；
- 有状态；
- 有错误信息；
- 可重试；
- 幂等。

## 重要架构规则

1. 原始文件 immutable。
2. AI analysis 是独立记录。
3. 用户修改写入 review/version，而不是覆盖原始 AI response。
4. 导出使用“已确认版本”。
5. 每个 AI 结果保存 provider、model、prompt_version、created_at。
