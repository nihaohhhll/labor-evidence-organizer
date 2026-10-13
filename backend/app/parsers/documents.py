"""Text extraction from uploaded documents.

PDF: use the embedded text layer first; pages without one are handed to OCR.
DOCX: paragraphs then tables. TXT: decoded as UTF-8.
Images: OCR only.

A parse failure never raises into the caller's happy path — it returns an
empty result with a reason, so the job can mark the file FAILED and the user
can retry (docs/03 §3, docs/12 Scenario 3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import docx  # python-docx
import pymupdf  # PyMuPDF (the `fitz` alias is deprecated)

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    text: str = ""
    pages: list[str] = field(default_factory=list)
    used_ocr: bool = False
    error: str | None = None


def parse_pdf(data: bytes, *, ocr_hook=None) -> ParsedDocument:
    """Extract text per page, falling back to OCR for scanned pages."""
    result = ParsedDocument()
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                page_text = page.get_text("text") or ""
                if not page_text.strip() and ocr_hook is not None:
                    try:
                        pix = page.get_pixmap(dpi=200)
                        page_text = ocr_hook(pix.tobytes("png")) or ""
                        result.used_ocr = True
                    except Exception as exc:  # pragma: no cover - OCR backend specific
                        logger.warning("OCR failed for a PDF page: %s", exc)
                result.pages.append(page_text)
            result.text = "\n\n".join(result.pages)
    except Exception as exc:
        logger.exception("PDF parse failed")
        result.error = f"PDF 解析失败：{exc}"
    return result


def parse_docx(data: bytes) -> ParsedDocument:
    """Extract paragraphs and table cells, preserving reading order."""
    result = ParsedDocument()
    try:
        import io

        doc = docx.Document(io.BytesIO(data))
        chunks: list[str] = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    chunks.append(" | ".join(cells))
        result.text = "\n".join(chunks)
        result.pages = [result.text]
    except Exception as exc:
        logger.exception("DOCX parse failed")
        result.error = f"DOCX 解析失败：{exc}"
    return result


def parse_txt(data: bytes) -> ParsedDocument:
    """Decode as UTF-8, tolerating a BOM and stray control characters."""
    result = ParsedDocument()
    try:
        text = data.decode("utf-8-sig", errors="replace")
        result.text = text
        result.pages = [text]
    except Exception as exc:  # pragma: no cover - decode with replace rarely fails
        logger.exception("TXT parse failed")
        result.error = f"文本解析失败：{exc}"
    return result


def parse_image(data: bytes, *, ocr_hook=None) -> ParsedDocument:
    """Images have no text layer; OCR is the only source."""
    result = ParsedDocument(used_ocr=True)
    if ocr_hook is None:
        result.error = None  # not an error: OCR simply unavailable
        return result
    try:
        result.text = ocr_hook(data) or ""
        result.pages = [result.text]
    except Exception as exc:
        logger.exception("Image OCR failed")
        result.error = f"图片识别失败：{exc}"
    return result


def parse_document(mime_type: str, data: bytes, *, ocr_hook=None) -> ParsedDocument:
    """Dispatch on MIME type. Unknown types yield an empty, non-fatal result."""
    if mime_type == "application/pdf":
        return parse_pdf(data, ocr_hook=ocr_hook)
    if mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return parse_docx(data)
    if mime_type == "text/plain":
        return parse_txt(data)
    if mime_type in ("image/png", "image/jpeg"):
        return parse_image(data, ocr_hook=ocr_hook)
    return ParsedDocument(error=f"暂不支持解析的类型：{mime_type}")
