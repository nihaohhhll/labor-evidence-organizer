"""Phase 3 unit tests: deterministic extraction, classification and parsers."""

from __future__ import annotations

import asyncio

from app.ai.mock import MockAIProvider, classify
from app.ai.providers import DocumentInput
from app.ai.rules import collect_hits, extract_amounts, extract_dates
from app.parsers.documents import parse_docx, parse_pdf, parse_txt
from tests.helpers import SAMPLE_TEXT, make_docx, make_pdf


# ---------- extraction rules ----------


def test_date_before_trigger_word_is_found():
    """Engineering log §3.2: "于2022年10月入职" must not be missed."""
    hits = extract_dates("本人于2022年10月入职该公司。")
    assert any(h.value.startswith("2022-10") for h in hits)


def test_date_after_trigger_word_is_found():
    hits = extract_dates("入职日期：2022年10月1日")
    assert hits[0].value == "2022-10-01"


def test_multiple_dates_are_all_reported_and_deduped():
    hits = extract_dates("2023年1月5日签合同，2023年1月5日发放工资，2024年6月离职。")
    values = [h.value for h in hits]
    assert values.count("2023-01-05") == 1  # deduped
    assert "2024-06-01" in values


def test_iso_and_slash_date_formats():
    hits = extract_dates("合同开始 2022-10-01，结束 2023/11/02")
    assert {h.value for h in hits} >= {"2022-10-01", "2023-11-02"}


def test_invalid_date_is_skipped():
    assert extract_dates("2022年13月45日") == []


def test_amounts_preserve_original_unit():
    amounts = [h.value for h in extract_amounts("月工资7500元，年终奖7,500.50元，补贴¥300")]
    assert "7500元" in amounts
    assert "7,500.50元" in amounts
    assert "¥300" in amounts


def test_collect_hits_returns_all_kinds():
    hits = collect_hits(SAMPLE_TEXT)
    assert hits.dates
    assert hits.amounts
    assert hits.organizations
    # Every fact keeps a source snippet for traceability.
    assert all(f.source for f in hits.facts)


# ---------- classification ----------


def test_classify_recognises_common_types():
    assert classify(SAMPLE_TEXT)[0] == "labor_contract"
    assert classify("关于解除劳动合同的通知")[0] == "company_notice"
    assert classify("微信聊天记录截图")[0] == "chat_record"
    assert classify("银行流水 交易明细 入账")[0] == "bank_statement"


def test_classify_returns_other_with_low_confidence():
    doc_type, confidence, _ = classify("随便一段没有特征的文字")
    assert doc_type == "other"
    assert confidence < 0.5


def test_confidence_is_bounded():
    for text in (SAMPLE_TEXT, "考勤打卡记录"):
        _, confidence, _ = classify(text)
        assert 0.0 <= confidence <= 1.0


# ---------- mock provider ----------


def test_mock_provider_is_deterministic():
    provider = MockAIProvider()
    doc = DocumentInput("a.txt", "text/plain", b"", SAMPLE_TEXT)
    first = asyncio.run(provider.analyze_document(doc))
    second = asyncio.run(provider.analyze_document(doc))
    assert first.document_type == second.document_type
    assert first.dates == second.dates
    assert first.provider == "mock"
    assert first.prompt_version == "evidence-extraction-v1"


def test_mock_provider_never_asserts_illegality():
    """docs/08: proof purpose must stay factual, never a legal conclusion."""
    provider = MockAIProvider()
    doc = DocumentInput("a.txt", "text/plain", b"", "公司于2024年1月1日通知我离职，月工资8000元")
    result = asyncio.run(provider.analyze_document(doc))
    banned = ("违法", "应当", "仲裁请求成立", "公司违反")
    for word in banned:
        assert word not in result.proof_purpose, result.proof_purpose


def test_mock_provider_handles_empty_text():
    provider = MockAIProvider()
    result = asyncio.run(provider.analyze_document(DocumentInput("a.txt", "text/plain", b"", "")))
    assert result.document_type == "other"
    assert result.summary  # still produces an honest, non-fabricated summary


def test_every_extracted_event_carries_a_source():
    provider = MockAIProvider()
    result = asyncio.run(provider.analyze_document(DocumentInput("a.txt", "text/plain", b"", SAMPLE_TEXT)))
    for event in result.events:
        assert "source" in event and event["source"]["file"] == "a.txt"


# ---------- parsers ----------


def test_parse_txt_preserves_content():
    parsed = parse_txt(SAMPLE_TEXT.encode())
    assert "劳动合同" in parsed.text
    assert parsed.error is None


def test_parse_pdf_extracts_text_layer():
    parsed = parse_pdf(make_pdf())
    assert parsed.error is None
    assert "劳动合同" in parsed.text
    assert len(parsed.pages) == 1


def test_parse_docx_extracts_paragraphs_and_tables():
    parsed = parse_docx(make_docx())
    assert parsed.error is None
    assert "劳动合同" in parsed.text
    assert "应发工资7500元" in parsed.text  # table cell content


def test_parse_corrupt_pdf_returns_error_not_exception():
    parsed = parse_pdf(b"%PDF-1.4 truncated garbage")
    # Either it parses nothing or it reports an error — never raises.
    assert parsed.error is not None or not parsed.text.strip()


def test_image_without_ocr_returns_empty_not_error():
    from app.parsers.documents import parse_image

    parsed = parse_image(b"\x89PNG\r\n\x1a\n", ocr_hook=None)
    assert parsed.text == ""
    assert parsed.error is None
    assert parsed.used_ocr is True


def test_unknown_mime_is_reported_not_raised():
    from app.parsers.documents import parse_document

    parsed = parse_document("application/zip", b"PK\x03\x04")
    assert parsed.error is not None
