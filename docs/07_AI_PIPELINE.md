# AI Pipeline

## Pipeline

File
→ Validation
→ Text/Image extraction
→ Classification
→ Structured extraction
→ Event extraction
→ Evidence suggestion
→ Human review

## Step 1 Validation

检查：
- MIME；
- 文件大小；
- 是否损坏；
- SHA-256。

## Step 2 Extraction

PDF：
- 优先提取文本；
- 无文本页面进入 OCR。

Image：
- OCR/Vision。

DOCX：
- 提取段落、表格。

## Step 3 Classification

输出 JSON：

```json
{
  "document_type": "company_notice",
  "confidence": 0.95,
  "reason": "..."
}
```

## Step 4 Structured Extraction

```json
{
  "dates": [],
  "amounts": [],
  "persons": [],
  "organizations": [],
  "events": [],
  "summary": ""
}
```

所有字段允许 null。

## Step 5 Event Extraction

事件必须引用 source_file/page/region（若可获得）。

## Step 6 Evidence Suggestion

生成：
- title
- category
- event_date
- summary
- proof_purpose

## 置信度策略

confidence < 0.80：
强制人工确认。

0.80 <= confidence < 0.95：
建议人工确认。

>= 0.95：
仍然允许人工修改，不自动视为事实正确。

## Prompt 规则

AI 必须：
1. 不编造不存在的信息；
2. 无法确认则 null；
3. 区分原文与推断；
4. 给出来源；
5. 不把法律结论写成事实；
6. 输出严格 JSON；
7. 不修改原始文件。

## Prompt Versioning

所有 prompt 保存版本号，例如：
`evidence-extraction-v1`

模型变化不得覆盖历史分析结果。
