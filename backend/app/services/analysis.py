"""Analysis pipeline: parse → classify → extract → persist.

Rules enforced here (docs/07_AI_PIPELINE):
* every analysis row records provider / model / prompt_version;
* re-analysis appends a new row and never mutates an old one;
* a file only reaches COMPLETED when an analysis succeeded.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import DocumentAnalysisResult, DocumentInput, OCRProvider
from app.ai.registry import get_ai_provider, get_ocr_provider
from app.config import settings
from app.models.analysis import DocumentAnalysis
from app.models.base import utcnow
from app.models.evidence import Evidence, ReviewStatus
from app.models.file import File, FileStatus
from app.parsers.documents import parse_document
from app.services.files import mark_completed, mark_failed, mark_processing

logger = logging.getLogger(__name__)

# Below this confidence a result must enter the human review queue
# (docs/07 §置信度策略).
FORCE_REVIEW_THRESHOLD = 0.80


class AnalysisError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run_async(coro):
    """Run a provider coroutine to completion.

    Must be called from a worker thread (routes are plain `def`), never from
    the event loop thread — hence the explicit guard instead of a bare
    `asyncio.run`, which would raise a confusing RuntimeError.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "analyze_file() 被在事件循环线程中调用；请通过同步路由或线程池调用。"
    )


def _make_ocr_hook(provider: OCRProvider):
    """Bridge the sync parser interface to the async OCR protocol."""

    def hook(png_bytes: bytes) -> str:
        result = _run_async(
            provider.extract(DocumentInput(filename="", mime_type="image/png", data=png_bytes))
        )
        return result.text

    return hook


def analyze_file(db: Session, file: File, *, provider_name: str | None = None) -> DocumentAnalysis:
    """Run the full pipeline for one file and persist the analysis row."""
    provider = get_ai_provider(provider_name)
    ocr = get_ocr_provider()

    mark_processing(db, file)

    try:
        from app.storage import get_storage

        data = get_storage().get(file.storage_key)
    except FileNotFoundError:
        mark_failed(db, file, "原始文件不存在，无法解析。")
        raise AnalysisError("CONTENT_MISSING", "原始文件不存在。") from None

    parsed = parse_document(file.mime_type, data, ocr_hook=_make_ocr_hook(ocr))
    if parsed.error:
        mark_failed(db, file, parsed.error)
        raise AnalysisError("PARSE_FAILED", parsed.error)

    document = DocumentInput(
        filename=file.original_filename,
        mime_type=file.mime_type,
        data=data,
        extracted_text=parsed.text,
    )

    try:
        result: DocumentAnalysisResult = _run_async(provider.analyze_document(document))
    except Exception as exc:
        logger.exception("AI provider failed for file %s", file.id)
        mark_failed(db, file, f"AI 解析失败：{exc}")
        raise AnalysisError("AI_FAILED", str(exc)) from exc

    analysis = DocumentAnalysis(
        file_id=file.id,
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version or settings.prompt_version,
        raw_text=result.raw_text or None,
        classification=result.document_type,
        classification_reason=result.type_reason or None,
        structured_json={
            "dates": result.dates,
            "amounts": result.amounts,
            "persons": result.persons,
            "organizations": result.organizations,
            "events": result.events,
            "summary": result.summary,
            "proof_purpose": result.proof_purpose,
        },
        confidence=result.confidence,
        status="SUCCESS",
    )
    db.add(analysis)
    db.flush()

    mark_completed(db, file)
    return analysis


def next_evidence_number(db: Session, case_id: uuid.UUID) -> int:
    """Allocate the next 1-based evidence number for a case.

    Uses the max existing number + 1 with a unique constraint as the backstop,
    so concurrent allocations cannot silently collide.
    """
    current = db.scalar(
        select(Evidence.evidence_number)
        .where(Evidence.case_id == case_id)
        .order_by(Evidence.evidence_number.desc())
        .limit(1)
    )
    return int(current or 0) + 1


def suggest_evidence_from_analysis(
    db: Session, case_id: uuid.UUID, analysis: DocumentAnalysis, *, file: File | None = None
) -> Evidence | None:
    """Turn one analysis into one editable Evidence row.

    The suggestion is marked PENDING so a human confirms it; nothing here is
    treated as a fact (docs/07 step 6, docs/14 法律相关).
    """
    structured = analysis.structured_json or {}

    # Re-analysis must not create a second row for the same source file —
    # update the existing suggestion instead (user edits are preserved via
    # user_edited_fields; only unedited fields get the new AI values).
    if file is not None:
        existing = db.scalar(
            select(Evidence)
            .where(Evidence.case_id == case_id, Evidence.source_file_id == file.id)
            .order_by(Evidence.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            edited = set(existing.edited_fields)
            existing.analysis_id = analysis.id
            existing.confidence = analysis.confidence
            if "summary" not in edited:
                existing.summary = structured.get("summary") or existing.summary
            if "proof_purpose" not in edited:
                existing.proof_purpose = structured.get("proof_purpose") or existing.proof_purpose
            if analysis.classification and "category" not in edited:
                existing.category = analysis.classification
            db.flush()
            _queue_review_items(db, case_id, existing, analysis)
            return existing

    event_date = None
    dates = structured.get("dates") or []
    if dates:
        from datetime import date as _date

        raw = str(dates[0]).strip()
        try:
            event_date = _date.fromisoformat(raw)
        except ValueError:
            # AI may return Chinese dates: 2022年3月1日 / 2026年8月
            import re as _re

            m = _re.match(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})", raw)
            if m:
                try:
                    event_date = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    event_date = None

    title = f"{analysis.classification or '材料'}—{(file.original_filename if file else '未命名')}"
    evidence = Evidence(
        case_id=case_id,
        source_file_id=file.id if file else None,
        analysis_id=analysis.id,
        evidence_number=next_evidence_number(db, case_id),
        title=title[:300],
        category=analysis.classification or "other",
        event_date=event_date,
        summary=(structured.get("summary") or None),
        proof_purpose=(structured.get("proof_purpose") or None),
        source_ref=file.original_filename if file else None,
        confidence=analysis.confidence,
        review_status=ReviewStatus.PENDING,
    )
    db.add(evidence)
    db.flush()

    # Anything below the confident threshold (and every proof_purpose, which is
    # the field users care most about) enters the human review queue.
    _queue_review_items(db, case_id, evidence, analysis)
    return evidence


def _queue_review_items(
    db: Session, case_id: uuid.UUID, evidence: Evidence, analysis: DocumentAnalysis
) -> None:
    """Create review items for the fields a human should check.

    docs/07 §置信度策略: below 0.80 review is mandatory; a proof_purpose is a
    *suggestion*, so it always needs a human look.
    """
    from app.models.review import ReviewItem

    structured = analysis.structured_json or {}
    needs_review = (analysis.confidence or 0.0) < FORCE_REVIEW_THRESHOLD

    fields: list[tuple[str, dict | None]] = [
        ("proof_purpose", {"proof_purpose": structured.get("proof_purpose")})
    ]
    if needs_review:
        fields += [
            ("summary", {"summary": structured.get("summary")}),
            ("category", {"category": evidence.category}),
        ]

    for field_name, ai_value in fields:
        db.add(
            ReviewItem(
                case_id=case_id,
                entity_type="evidence",
                entity_id=evidence.id,
                field_name=field_name,
                ai_value=ai_value,
                user_value=None,
                status="PENDING",
                confidence=analysis.confidence,
            )
        )
    db.flush()


def analyze_case_files(
    db: Session, case_id: uuid.UUID, file_ids: list[uuid.UUID] | None = None
) -> list[DocumentAnalysis]:
    """Analyze every pending file in a case and emit evidence suggestions."""
    stmt = select(File).where(
        File.case_id == case_id,
        File.deleted_at.is_(None),
        File.status.in_([FileStatus.UPLOADED.value, FileStatus.QUEUED.value]),
    )
    if file_ids:
        stmt = stmt.where(File.id.in_(file_ids))
    files = list(db.scalars(stmt).all())

    results: list[DocumentAnalysis] = []
    for file in files:
        try:
            analysis = analyze_file(db, file)
        except AnalysisError:
            continue  # file already marked FAILED; keep going
        suggest_evidence_from_analysis(db, case_id, analysis, file=file)
        results.append(analysis)

    db.commit()
    return results


def latest_analysis(db: Session, file_id: uuid.UUID) -> DocumentAnalysis | None:
    """Most recent successful analysis for a file (never rewritten in place)."""
    return db.scalar(
        select(DocumentAnalysis)
        .where(DocumentAnalysis.file_id == file_id, DocumentAnalysis.status == "SUCCESS")
        .order_by(DocumentAnalysis.created_at.desc())
        .limit(1)
    )
