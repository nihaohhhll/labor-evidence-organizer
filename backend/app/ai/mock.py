"""Mock AI / OCR providers.

These are the default providers for development and tests: deterministic,
offline and incapable of inventing facts. Swap them for a real vendor by
setting `AI_PROVIDER` / `OCR_PROVIDER` — business code does not change.
"""

from __future__ import annotations

import re

from app.ai.providers import (
    AIProvider,
    DocumentAnalysisResult,
    DocumentInput,
    OCRProvider,
    OCRResult,
)
from app.ai.rules import collect_hits

# (keyword list, document_type, reason). Scored, not first-match: the winner is
# the type with the most distinct keyword hits, which stops "劳动合同" from
# swallowing "解除劳动合同通知书" just because it appears first.
DOCUMENT_TYPE_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("解除劳动合同", "辞退", "开除", "解聘", "通知书", "通知"), "company_notice", "出现公司通知类表述"),
    (("劳动合同", "劳动协议", "合同期限", "试用期"), "labor_contract", "出现劳动合同专用表述"),
    (("微信", "聊天", "群聊", "[图片]", "撤回"), "chat_record", "出现聊天记录特征"),
    (("流水", "交易", "余额", "入账", "代发"), "bank_statement", "出现银行流水特征"),
    (("工资条", "应发", "实发", "基本工资", "绩效"), "salary_statement", "出现工资构成表述"),
    (("考勤", "打卡", "出勤", "迟到", "请假"), "attendance_record", "出现考勤表述"),
    (("社保", "公积金", "缴纳", "参保"), "social_insurance", "出现社保表述"),
    (("身份证", "住址", "公民身份号码"), "identity_document", "出现身份证表述"),
    (("统一社会信用代码", "注册资本", "法定代表人"), "company_registration", "出现工商登记表述"),
]

# Keywords that mark a document as a notice even when a contract term appears.
_NOTICE_HINTS = ("通知", "告知", "决定", "即日", "特此")

PROOF_PURPOSE_BY_TYPE: dict[str, str] = {
    "labor_contract": "用于证明双方存在劳动关系及约定的岗位、工资、期限这一事实。",
    "company_notice": "用于证明公司于材料所载日期发布该通知这一事实。",
    "chat_record": "用于证明双方于材料所载时间就相关事宜进行沟通这一事实。",
    "bank_statement": "用于证明材料所载期间存在工资款项收付这一事实。",
    "salary_statement": "用于证明材料所载月份的工资构成与金额这一事实。",
    "attendance_record": "用于证明材料所载期间的出勤情况这一事实。",
    "social_insurance": "用于证明材料所载期间的社保缴纳情况这一事实。",
    "identity_document": "用于证明材料所载人员的身份信息这一事实。",
    "company_registration": "用于证明被申请人的工商登记信息这一事实。",
    "work_record": "用于证明材料所载的工作内容与过程这一事实。",
    "other": "用于证明材料所载内容这一事实。",
}

# Structural signal for chat logs: several lines each prefixed with a
# date+time. Keyword matching alone misses this, because a long chat that
# mentions 「辞退」 scores higher on the notice rules even though the document
# is plainly a conversation transcript.
_LINE_TIMESTAMP = re.compile(
    r"^\s*\[?(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}\s+\d{1,2}:\d{2})\]?", re.MULTILINE
)

# Markers that identify a document as instructions rather than evidence.
# Text like 「IGNORE ALL PREVIOUS INSTRUCTIONS」 or 「SYSTEM: ...」 is not
# material a worker would submit, so it must never be classified confidently.
_INSTRUCTION_MARKERS = (
    "ignore all previous",
    "ignore previous",
    "system:",
    "you are now",
    "忽略以上指令",
    "忽略前述",
    "系统提示",
    "按我说的",
    "输出以下内容",
    "pretend you",
)

# Confidence ceiling for instruction-shaped input. Kept well below the review
# threshold so it always reaches a human instead of being trusted.
_INSTRUCTION_CONFIDENCE_CAP = 0.35


def _chat_structural_score(text: str) -> int:
    """Score how much the text looks like a chat transcript."""
    timestamps = len(_LINE_TIMESTAMP.findall(text))
    if timestamps >= 5:
        return 3
    if timestamps >= 2:
        return 2
    return 0


# Common OCR confusions. Applied before classification as a fallback pass,
# so 「劳动合司」(OCR of 劳动合同) and 「2022年l0月」 still resolve. Only
# applied when the un-normalised text classified as `other` — a clean
# document must never be re-read through the error-prone lens.
_OCR_DIGIT_CONFUSIONS = str.maketrans({
    "l": "1", "I": "1", "|": "1",
    "O": "0", "o": "0",
    "S": "5", "s": "5",
    "B": "8", "b": "8",
    "Z": "2", "z": "2",
})

# (typo produced by OCR, correct characters). Kept short and defensible:
# each pair is a documented confusion, not a guess.
_OCR_WORD_CONFUSIONS: tuple[tuple[str, str], ...] = (
    ("劳动合司", "劳动合同"),
    ("劳动台同", "劳动合同"),
    ("劳动台司", "劳动合同"),
    ("月工咨", "月工资"),
    ("工咨", "工资"),
    ("考勤表", "考勤"),
    ("银丁流水", "银行流水"),
    ("银斤流水", "银行流水"),
    ("社保", "社保"),
)


def _normalize_ocr(text: str) -> str:
    """Best-effort repair of OCR noise so keyword rules can still fire."""
    repaired = text
    for typo, correct in _OCR_WORD_CONFUSIONS:
        repaired = repaired.replace(typo, correct)
    # Digit confusions only apply inside digit runs, so ordinary prose
    # (and Chinese text) is untouched.
    repaired = re.sub(
        r"(?<=\d)[lIoOsSbBzZ]|(?<=[lIoOsSbBzZ])(?=\d)",
        lambda m: m.group(0).translate(_OCR_DIGIT_CONFUSIONS),
        repaired,
    )
    # 「2022年l0月」 — a letter standing in for a digit next to 年/月.
    repaired = re.sub(
        r"(?<=年)[lIoOsSbBzZ](?=月)",
        lambda m: m.group(0).translate(_OCR_DIGIT_CONFUSIONS),
        repaired,
    )
    return repaired


def _is_instruction_shaped(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _INSTRUCTION_MARKERS)


def classify(text: str) -> tuple[str, float, str]:
    """Return (document_type, confidence, reason) by scoring every rule.

    Three guards, each earned by a real failure mode:

    1. **Scoring, not first-match.** Chinese keywords nest — "劳动合同" is a
       substring of "解除劳动合同" — so an ordered scan would call a
       termination notice a contract.
    2. **Structural chat detection.** A long transcript mentioning "辞退"
       out-scores the chat keywords, even though it is obviously a
       conversation. Line-level timestamps are the reliable signal.
    3. **Instruction-shaped input is never confident.** A document whose body
       is "IGNORE ALL PREVIOUS INSTRUCTIONS…" is not evidence, whatever
       phrases it quotes. It is capped below the review threshold so it
       always reaches a human.
    """
    if _is_instruction_shaped(text):
        return (
            "other",
            _INSTRUCTION_CONFIDENCE_CAP,
            "内容为指令式文本而非证据材料，已降级并转入人工确认",
        )

    best_type, best_score, best_reason = "other", 0, "未命中任何已知类型关键词"

    for keywords, doc_type, reason in DOCUMENT_TYPE_RULES:
        score = sum(1 for k in keywords if k in text)
        if score == 0:
            continue
        # A notice-word bonus breaks ties in favour of the more specific type.
        if doc_type == "company_notice" and any(h in text for h in _NOTICE_HINTS):
            score += 1
        if score > best_score:
            best_type, best_score, best_reason = doc_type, score, reason

    # Chat is scored on structure as well as keywords, so a transcript that
    # merely mentions notice-related words ("能给书面通知吗") still wins as a
    # chat record. Structure is the more reliable signal, so it also breaks
    # ties rather than losing them to scattered keywords.
    chat_score = _chat_structural_score(text)
    if chat_score >= best_score:
        best_type = "chat_record"
        best_score = chat_score
        best_reason = "检测到多行时间戳，符合聊天记录结构"

    if best_score == 0:
        # Nothing matched on the clean text: try once more through the OCR
        # repair pass, which is deliberately only reached here so that clean
        # documents are never scored against fuzzy variants.
        normalized = _normalize_ocr(text)
        if normalized != text:
            for keywords, doc_type, reason in DOCUMENT_TYPE_RULES:
                score = sum(1 for k in keywords if k in normalized)
                if score == 0:
                    continue
                if doc_type == "company_notice" and any(h in normalized for h in _NOTICE_HINTS):
                    score += 1
                if score > best_score:
                    best_type, best_score = doc_type, score
                    best_reason = f"{reason}（已容错处理 OCR 误识）"

    if best_score == 0:
        return "other", 0.3, best_reason

    # More distinct signals => higher confidence, capped below certainty:
    # docs/07 says even >= 0.95 stays human-editable. OCR-repaired matches
    # score lower because they rest on inferred text.
    confidence = min(0.72 + 0.08 * best_score, 0.97)
    if "OCR 误识" in best_reason:
        confidence = min(confidence, 0.72)
    return best_type, round(confidence, 2), best_reason


def build_summary(text: str, doc_type: str, orgs: list[str], dates: list[str], amounts: list[str]) -> str:
    """Compose a factual summary. Never asserts a legal conclusion."""
    parts: list[str] = []
    if orgs:
        parts.append(f"材料中出现组织：{'、'.join(orgs[:3])}")
    if dates:
        parts.append(f"材料中出现日期：{'、'.join(dates[:3])}")
    if amounts:
        parts.append(f"材料中出现金额：{'、'.join(amounts[:3])}")
    if not parts:
        head = re.sub(r"\s+", " ", text).strip()[:60]
        return f"材料中未提取到明确的日期、金额或组织。原文片段：{head}" if head else "材料内容为空或无法识别。"
    return "；".join(parts) + "。"


class MockAIProvider:
    """Deterministic offline stand-in for a vision/LLM provider."""

    name = "mock"
    model = "mock-rules-1"
    prompt_version = "evidence-extraction-v1"

    async def analyze_document(self, document: DocumentInput) -> DocumentAnalysisResult:
        text = document.extracted_text or ""
        hits = collect_hits(text)
        doc_type, confidence, reason = classify(text)
        summary = build_summary(text, doc_type, hits.organizations, hits.dates, hits.amounts)

        events = []
        for fact in hits.facts[:10]:
            events.append(
                {
                    "kind": fact.kind,
                    "value": fact.value,
                    "excerpt": fact.source,
                    # Explicitly marked as derived, not quoted verbatim.
                    "source": {"file": document.filename, "region": None},
                }
            )

        return DocumentAnalysisResult(
            document_type=doc_type,
            type_confidence=confidence,
            type_reason=reason,
            raw_text=text,
            dates=hits.dates,
            amounts=hits.amounts,
            persons=hits.persons,
            organizations=hits.organizations,
            events=events,
            summary=summary,
            # Neutral by construction: the mock never asserts illegality.
            proof_purpose=PROOF_PURPOSE_BY_TYPE.get(doc_type, PROOF_PURPOSE_BY_TYPE["other"]),
            confidence=confidence,
            provider=self.name,
            model=self.model,
            prompt_version=self.prompt_version,
        )


class MockOCRProvider:
    """No-op OCR: returns empty text so callers treat images as opaque."""

    name = "mock"
    model = "mock-ocr-1"

    async def extract(self, document: DocumentInput) -> OCRResult:
        # Mock has no vision capability; a real provider would call an API.
        return OCRResult(text="", confidence=0.0, provider=self.name, model=self.model)
