"""OpenAI-compatible AI provider.

Talks to any OpenAI-compatible `/v1/chat/completions` endpoint. The prompt
follows docs/08_PROMPT_SPEC.md: structured extraction only, no legal
conclusions, null for unknown fields.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.ai.mock import PROOF_PURPOSE_BY_TYPE, classify
from app.ai.providers import (
    AIProvider,
    DocumentAnalysisResult,
    DocumentInput,
)
from app.config import settings

logger = logging.getLogger(__name__)

_PROMPT_VERSION = "evidence-extraction-v1"

_SYSTEM_PROMPT = (
    "你是证据材料结构化解析助手。\n"
    "任务：从用户提供的原始材料中提取明确存在的信息。\n"
    "严格要求：\n"
    "- 不得编造；\n"
    "- 不确定字段返回 null；\n"
    "- 日期必须来自材料；\n"
    "- 金额必须保留原始单位；\n"
    "- 不得把法律评价当作事实；\n"
    "- 每个事件必须尽可能引用来源；\n"
    "- 输出严格 JSON，不要输出任何其他文本。\n\n"
    "输出 JSON schema：\n"
    "{\n"
    '  "document_type": "labor_contract|company_notice|chat_record|bank_statement|'
    'salary_statement|attendance_record|social_insurance|identity_document|'
    'company_registration|work_record|other",\n'
    '  "type_confidence": 0.0-1.0,\n'
    '  "type_reason": "简短理由",\n'
    '  "raw_text": "材料原文关键内容",\n'
    '  "dates": ["YYYY-MM-DD 或原文日期格式"],\n'
    '  "amounts": ["原文金额，保留单位"],\n'
    '  "persons": ["人名"],\n'
    '  "organizations": ["组织/公司名"],\n'
    '  "events": [{"kind": "事件类型", "value": "事件描述", "excerpt": "原文引用", '
    '"source": {"file": "文件名", "region": null}}],\n'
    '  "summary": "事实性摘要，不包含法律评价",\n'
    '  "proof_purpose": "用于证明……这一事实。",\n'
    '  "confidence": 0.0-1.0\n'
    "}"
)

_ALLOWED_TYPES = {
    "labor_contract",
    "company_notice",
    "chat_record",
    "bank_statement",
    "salary_statement",
    "attendance_record",
    "social_insurance",
    "identity_document",
    "company_registration",
    "work_record",
    "other",
}


def _clean_json(raw: str) -> dict[str, Any]:
    """Extract a JSON object from the model output, tolerating markdown fences."""
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Find the first { ... last }.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object in model output: {raw[:200]!r}")
    return json.loads(text[start : end + 1])


class OpenAIProvider:
    """Sends document text to an OpenAI-compatible chat completions endpoint."""

    def __init__(self) -> None:
        self.name = "openai"
        self.model = settings.ai_model or "kilo-auto/free"
        self.prompt_version = _PROMPT_VERSION
        self._base_url = (settings.ai_base_url or "http://127.0.0.1:6449").rstrip("/")
        self._api_key = settings.ai_api_key or "free-proxy-key"

    async def analyze_document(self, document: DocumentInput) -> DocumentAnalysisResult:
        text = (document.extracted_text or "").strip()
        if not text:
            # No text layer (e.g. image): fall back to rule-based mock.
            from app.ai.mock import MockAIProvider

            return await MockAIProvider().analyze_document(document)

        user_content = f"文件名：{document.filename}\nMIME：{document.mime_type}\n\n材料内容：\n{text[:8000]}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                body = resp.json()

            raw_output = body["choices"][0]["message"]["content"]
            data = _clean_json(raw_output)
        except Exception:
            logger.exception("OpenAI provider failed for %s, falling back to rules", document.filename)
            from app.ai.mock import MockAIProvider

            return await MockAIProvider().analyze_document(document)

        doc_type = data.get("document_type") or "other"
        if doc_type not in _ALLOWED_TYPES:
            doc_type = "other"

        try:
            type_conf = float(data.get("type_confidence") or 0.0)
        except (TypeError, ValueError):
            type_conf = 0.0

        try:
            conf = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0

        def _str_list(val: Any) -> list[str]:
            if not isinstance(val, list):
                return []
            return [str(v) for v in val if v]

        events_raw = data.get("events") or []
        events: list[dict[str, Any]] = []
        if isinstance(events_raw, list):
            for ev in events_raw[:20]:
                if not isinstance(ev, dict):
                    continue
                events.append(
                    {
                        "kind": str(ev.get("kind") or ""),
                        "value": str(ev.get("value") or ""),
                        "excerpt": str(ev.get("excerpt") or ""),
                        "source": {
                            "file": document.filename,
                            "region": ev.get("source", {}).get("region") if isinstance(ev.get("source"), dict) else None,
                        },
                    }
                )

        proof_purpose = str(data.get("proof_purpose") or "").strip()
        if not proof_purpose:
            proof_purpose = PROOF_PURPOSE_BY_TYPE.get(doc_type, PROOF_PURPOSE_BY_TYPE["other"])

        # Enforce prompt spec: proof_purpose must not contain legal conclusions.
        illegal_markers = ("违法", "违约", "应当赔偿", "非法解除")
        if any(m in proof_purpose for m in illegal_markers):
            proof_purpose = PROOF_PURPOSE_BY_TYPE.get(doc_type, PROOF_PURPOSE_BY_TYPE["other"])

        return DocumentAnalysisResult(
            document_type=doc_type,
            type_confidence=type_conf,
            type_reason=str(data.get("type_reason") or ""),
            raw_text=str(data.get("raw_text") or text[:2000]),
            dates=_str_list(data.get("dates")),
            amounts=_str_list(data.get("amounts")),
            persons=_str_list(data.get("persons")),
            organizations=_str_list(data.get("organizations")),
            events=events,
            summary=str(data.get("summary") or ""),
            proof_purpose=proof_purpose,
            confidence=conf,
            provider=self.name,
            model=self.model,
            prompt_version=self.prompt_version,
        )
