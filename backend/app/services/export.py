"""Export service: render the evidence index, timeline and bundle.

Numbering and pagination rules (docs/10_DOCUMENT_GENERATION):
* evidence is numbered 证据1, 证据2 … (multi-page: 证据1-1, 证据1-2);
* every page reads 第 X 页 / 共 Y 页;
* ordering is decided by `evidence_number`, never by insertion order;
* only confirmed/user-reviewed data is read.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from docx import Document as DocxDocument
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_gap import CaseEvidenceGapResult
from app.models.evidence import Evidence
from app.models.event import Event
from app.models.export import ExportJob, ExportStatus
from app.models.material_package import MaterialPackage, MaterialPackageSnapshot
from app.parsers.documents import parse_document
from app.storage import get_storage

EXPORT_FORMATS = ("docx", "pdf", "zip")
# Phase 9-C: package exports never bundle ZIPs (decision 4.2).
PACKAGE_EXPORT_FORMATS = ("docx", "pdf")

# CJK-capable font shipped with ReportLab; avoids tofu boxes in the PDF.
CJK_FONT = "STSong-Light"

DISCLAIMER = "本文件由证据整理工具生成，内容仅供参考，不构成正式法律意见。"


class ExportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_filename(name: str, limit: int = 40) -> str:
    """Strip path separators and control chars from a case name."""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name).strip() or "案件"
    return cleaned[:limit]


def export_filename(case_name: str, fmt: str) -> str:
    return f"证据包-{_safe_filename(case_name)}.{fmt}"


def _page_footer(canvas, doc):
    """Render 第 X 页 / 共 Y 页 on every page."""
    canvas.saveState()
    canvas.setFont(CJK_FONT, 9)
    canvas.drawCentredString(A4[0] / 2, 10 * mm, f"第 {canvas.getPageNumber()} 页 / 共 {doc.page} 页")
    canvas.restoreState()


def _ensure_cjk_font() -> None:
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))
    except Exception:  # pragma: no cover - already registered
        pass


@dataclass
class ExportData:
    case: Case
    evidence: list[Evidence]
    events: list[Event]
    generated_at: datetime


def _rows(evidence: list[Evidence]) -> list[list[str]]:
    """证据目录 table rows: 编号 | 证据名称 | 形成时间 | 证明目的."""
    header = ["编号", "证据名称", "形成时间", "证明目的"]
    body = [
        [
            f"证据{e.evidence_number}",
            e.title,
            e.event_date.isoformat() if e.event_date else "时间未知",
            e.proof_purpose or "（待补充）",
        ]
        for e in sorted(evidence, key=lambda x: x.evidence_number)
    ]
    return [header, *body]


def _timeline_rows(events: list[Event]) -> list[list[str]]:
    header = ["日期", "事件", "来源证据"]
    body = []
    for ev in sorted(events, key=lambda x: (x.event_date is None, x.event_date)):
        sources = "、".join(f"证据{m.evidence_number}" for m in ev.evidence) or "—"
        body.append(
            [
                ev.event_date.isoformat() if ev.event_date else "时间未知",
                ev.title,
                sources,
            ]
        )
    return [header, *body]


def render_docx(data: ExportData) -> bytes:
    """Render 证据目录 + 时间轴 into a Word document."""
    doc = DocxDocument()
    style = doc.styles["Normal"]
    style.font.name = "SimSun"
    style.font.size = Pt(10.5)

    doc.add_heading(f"证据目录 — {data.case.name}", level=1)
    doc.add_paragraph(f"生成时间：{data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    doc.add_paragraph(DISCLAIMER)
    doc.add_paragraph()

    table = doc.add_table(rows=0, cols=4)
    table.style = "Table Grid"
    for i, row in enumerate(_rows(data.evidence)):
        cells = table.add_row().cells
        for j, value in enumerate(row):
            cells[j].text = value
            if i == 0:
                for run in cells[j].paragraphs[0].runs:
                    run.bold = True

    doc.add_paragraph()
    doc.add_heading("案件时间轴", level=1)
    t2 = doc.add_table(rows=0, cols=3)
    t2.style = "Table Grid"
    for row in _timeline_rows(data.events):
        cells = t2.add_row().cells
        for j, value in enumerate(row):
            cells[j].text = value

    for section in doc.sections:
        section.footer.paragraphs[0].text = DISCLAIMER

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_pdf(data: ExportData) -> bytes:
    """Render the same content to PDF with page numbers."""
    _ensure_cjk_font()
    buf = io.BytesIO()
    story = []

    story.append(Paragraph(f"证据目录 — {data.case.name}", _heading_style(16)))
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"生成时间：{data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", _heading_style(9)
        )
    )
    story.append(Paragraph(DISCLAIMER, _heading_style(9)))
    story.append(Spacer(1, 6 * mm))

    index_rows = [
        [Paragraph(str(c), _heading_style(9)) for c in row] for row in _rows(data.evidence)
    ]
    index = Table(index_rows, colWidths=[18 * mm, 55 * mm, 28 * mm, 65 * mm], repeatRows=1)
    index.setStyle(_table_style())
    story.append(index)

    if data.events:
        story.append(PageBreak())
        story.append(Paragraph("案件时间轴", _heading_style(14)))
        story.append(Spacer(1, 5 * mm))
        tl_rows = [
            [Paragraph(str(c), _heading_style(9)) for c in row]
            for row in _timeline_rows(data.events)
        ]
        tl = Table(tl_rows, colWidths=[28 * mm, 92 * mm, 46 * mm], repeatRows=1)
        tl.setStyle(_table_style())
        story.append(tl)

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()


def _heading_style(size: int):
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle(
        name=f"h{size}",
        fontName=CJK_FONT,
        fontSize=size,
        leading=size * 1.5,
    )


def _table_style():
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), CJK_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def render_zip(data: ExportData, *, docx_bytes: bytes, pdf_bytes: bytes) -> bytes:
    """Bundle the documents plus the originals, ordered by evidence_number."""
    from app.storage import get_storage as _gs

    buf = io.BytesIO()
    storage = _gs()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("证据目录.docx", docx_bytes)
        zf.writestr("证据目录.pdf", pdf_bytes)
        zf.writestr(
            "证据索引.csv",
            "编号,证据名称,形成时间,证明目的\n"
            + "\n".join(
                f"证据{e.evidence_number},{_csv_cell(e.title)},"
                f"{e.event_date.isoformat() if e.event_date else '时间未知'},"
                f"{_csv_cell(e.proof_purpose or '')}"
                for e in sorted(data.evidence, key=lambda x: x.evidence_number)
            ),
        )
        for e in sorted(data.evidence, key=lambda x: x.evidence_number):
            if not e.source_file or e.source_file.deleted_at is not None:
                continue
            try:
                original = storage.get(e.source_file.storage_key)
            except FileNotFoundError:
                continue  # original missing; the index still lists it
            zf.writestr(f"原始文件/证据{e.evidence_number}-{e.source_file.original_filename}", original)
    return buf.getvalue()


def _csv_cell(value: str) -> str:
    """Escape a CSV field (quotes and newlines)."""
    return '"' + value.replace('"', '""').replace("\n", " ") + '"'


def build_export(
    db: Session,
    case: Case,
    fmt: str,
    *,
    evidence: list[Evidence],
    events: list[Event],
) -> ExportJob:
    """Render, store and record one export job."""
    if fmt not in EXPORT_FORMATS:
        raise ExportError("UNSUPPORTED_FORMAT", f"不支持的导出格式：{fmt}")

    data = ExportData(
        case=case,
        evidence=evidence,
        events=events,
        generated_at=datetime.now(timezone.utc),
    )
    job = ExportJob(case_id=case.id, format=fmt, status=ExportStatus.RUNNING)
    if fmt == "docx":
        return _run_job(db, job, lambda: render_docx(data))
    if fmt == "pdf":
        return _run_job(db, job, lambda: render_pdf(data))
    return _run_job(
        db,
        job,
        lambda: render_zip(data, docx_bytes=render_docx(data), pdf_bytes=render_pdf(data)),
    )


def _run_job(db: Session, job: ExportJob, render_fn) -> ExportJob:
    """Shared job lifecycle: persist RUNNING, render, store, mark COMPLETED.

    Extracted in Phase 9-C so package exports reuse the exact Phase 7
    failure-recording behaviour (FAILED row + RENDER_FAILED) instead of
    duplicating it.
    """
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        payload = render_fn()
    except Exception as exc:  # pragma: no cover - renderer internals
        job.status = ExportStatus.FAILED
        job.error_message = str(exc)[:1024]
        db.commit()
        raise ExportError("RENDER_FAILED", f"导出生成失败：{exc}") from exc

    key = f"cases/{job.case_id}/exports/{job.id}.{job.format}"
    get_storage().put(key, payload)

    job.storage_key = key
    job.status = ExportStatus.COMPLETED
    from app.models.base import utcnow

    job.completed_at = utcnow()
    db.commit()
    db.refresh(job)
    return job


# ---------- Phase 9-C: material package exports (成卷输出) ----------

_MAX_RASTER_PAGES = 30  # scanned PDF pages converted to images per file

GAP_APPENDIX_TITLE = "附录：材料完整性提示（系统生成）"
GAP_APPENDIX_LEAD = (
    "以下为工具辅助生成的材料完整性提示，仅供参考，不构成事实认定、"
    "法律结论或对任何材料的确认；请以原始材料为准。"
)


def package_export_filename(package_name: str, fmt: str) -> str:
    return f"材料包-{_safe_filename(package_name)}.{fmt}"


@dataclass
class ContentPart:
    """One renderable piece of an item's original evidence."""

    kind: str  # "text" | "image"
    text: str = ""
    image: bytes | None = None


@dataclass
class ContentBlock:
    """Converted original content for one package item.

    `notes` are explicit markers (missing file, unsupported type, page cap…)
    so unusable originals are always visible, never silently dropped.
    """

    parts: list[ContentPart] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PackageRow:
    display_number: int
    display_name: str
    proof_purpose: str | None
    evidence_number: int | None
    evidence_id: uuid.UUID


@dataclass
class AppendixData:
    generated_at: datetime
    stale: bool
    missing_items: list[dict]  # {"title","description"} only
    version: int


@dataclass
class PackageExportData:
    case: Case
    package: MaterialPackage
    rows: list[PackageRow]
    contents: dict[uuid.UUID, ContentBlock]
    generated_at: datetime
    appendix: AppendixData | None = None


def _rows_from_snapshot(snapshot: MaterialPackageSnapshot) -> list[PackageRow]:
    rows: list[PackageRow] = []
    for item in snapshot.content.get("items", []):
        rows.append(
            PackageRow(
                display_number=int(item.get("display_number") or 0),
                display_name=str(item.get("display_name") or ""),
                proof_purpose=item.get("proof_purpose"),
                evidence_number=item.get("evidence_number"),
                evidence_id=uuid.UUID(str(item["evidence_id"])),
            )
        )
    rows.sort(key=lambda r: r.display_number)
    return rows


def _pdf_content(data: bytes) -> ContentBlock:
    """PDF: text pages as text, scanned pages rasterised (faithful, no OCR).

    Empty pages beyond the cap are reported explicitly instead of dropped.
    """
    import pymupdf

    parts: list[ContentPart] = []
    notes: list[str] = []
    rasterized = 0
    skipped = 0
    total_pages = 0
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            total_pages = len(doc)
            for page in doc:
                text = page.get_text("text") or ""
                if text.strip():
                    parts.append(ContentPart(kind="text", text=text))
                    continue
                if rasterized < _MAX_RASTER_PAGES:
                    pix = page.get_pixmap(dpi=144)
                    parts.append(ContentPart(kind="image", image=pix.tobytes("png")))
                    rasterized += 1
                else:
                    skipped += 1
    except Exception as exc:
        return ContentBlock(notes=[f"PDF 解析失败，无法转换：{exc}"])
    if skipped:
        notes.append(
            f"扫描页转换已达上限（{_MAX_RASTER_PAGES} 页/文件），"
            f"另有 {skipped} 页未转换（该文件共 {total_pages} 页），请查阅原始文件。"
        )
    if not parts:
        notes.append("该 PDF 没有可转换的内容。")
    return ContentBlock(parts=parts, notes=notes)


def convert_original(evidence: Evidence, data: bytes) -> ContentBlock:
    """Convert one original file into renderable parts (never raises)."""
    mime = evidence.source_file.mime_type if evidence.source_file else ""
    if mime in ("image/png", "image/jpeg"):
        # Embed the picture itself — the image *is* the original evidence;
        # mock OCR text would not be.
        return ContentBlock(parts=[ContentPart(kind="image", image=data)])
    if mime == "application/pdf":
        return _pdf_content(data)
    parsed = parse_document(mime, data, ocr_hook=None)
    if parsed.error:
        return ContentBlock(notes=[f"【原始文件无法可靠转换为正文】{parsed.error}，请查阅原始文件。"])
    if not parsed.text.strip():
        return ContentBlock(notes=[f"【原始文件无法可靠转换为正文】{mime} 解析结果为空，请查阅原始文件。"])
    return ContentBlock(parts=[ContentPart(kind="text", text=parsed.text)])


def build_contents(rows: list[PackageRow], evidence_map: dict[uuid.UUID, Evidence]) -> dict[uuid.UUID, ContentBlock]:
    storage = get_storage()
    contents: dict[uuid.UUID, ContentBlock] = {}
    for row in rows:
        ev = evidence_map.get(row.evidence_id)
        if ev is None:
            contents[row.evidence_id] = ContentBlock(
                notes=["来源证据已被删除，无法获取原始内容。"]
            )
            continue
        sf = ev.source_file
        if sf is not None and sf.deleted_at is not None:
            contents[row.evidence_id] = ContentBlock(
                notes=[f"【原始文件无法可靠转换为正文】原始文件已删除（{sf.original_filename}），请查阅原始文件。"]
            )
            continue
        if sf is None:
            if ev.summary:
                contents[row.evidence_id] = ContentBlock(
                    parts=[
                        ContentPart(
                            kind="text",
                            text=f"（手工录入记录，无原始文件）\n{ev.summary}",
                        )
                    ]
                )
            else:
                contents[row.evidence_id] = ContentBlock(
                    notes=["该证据无关联原始文件，也没有记录摘要，没有可嵌入的原始内容。"]
                )
            continue
        try:
            data = storage.get(sf.storage_key)
        except FileNotFoundError:
            contents[row.evidence_id] = ContentBlock(
                notes=[f"【原始文件无法可靠转换为正文】原始文件已不存在（{sf.original_filename}），请查阅原始文件。"]
            )
            continue
        try:
            contents[row.evidence_id] = convert_original(ev, data)
        except Exception as exc:  # per-item isolation: one bad file must not fail the whole volume
            contents[row.evidence_id] = ContentBlock(
                notes=[f"【原始文件无法可靠转换为正文】转换失败：{exc}，请查阅原始文件。"]
            )
    return contents


def list_package_exports(
    db: Session, package_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[ExportJob], int]:
    total = (
        db.scalar(
            select(func.count(ExportJob.id)).where(ExportJob.package_id == package_id)
        )
        or 0
    )
    rows = list(
        db.scalars(
            select(ExportJob)
            .where(ExportJob.package_id == package_id)
            .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return rows, total


def latest_gap_result(db: Session, case_id: uuid.UUID) -> CaseEvidenceGapResult | None:
    """Latest A3 result, or None when unavailable (none/failed/no json)."""
    row = db.scalar(
        select(CaseEvidenceGapResult)
        .where(CaseEvidenceGapResult.case_id == case_id)
        .order_by(CaseEvidenceGapResult.version.desc())
        .limit(1)
    )
    if row is None or row.status != "SUCCESS" or not row.gap_json:
        return None
    return row


def build_appendix(db: Session, gap_result: CaseEvidenceGapResult) -> AppendixData:
    missing = (gap_result.gap_json or {}).get("missing_items") or []
    items = [
        {
            "title": str(m.get("title") or "未命名提示"),
            "description": str(m.get("description") or ""),
        }
        for m in missing
        if isinstance(m, dict)
    ]
    latest_edit = db.scalar(
        select(func.max(Evidence.updated_at)).where(Evidence.case_id == gap_result.case_id)
    )
    stale = bool(
        latest_edit is not None
        and gap_result.created_at is not None
        and latest_edit > gap_result.created_at
    )
    return AppendixData(
        generated_at=gap_result.created_at or datetime.now(timezone.utc),
        stale=stale,
        missing_items=items,
        version=gap_result.version,
    )


# ---------- package renderers (DOCX / PDF) ----------


def _package_index_rows(rows: list[PackageRow]) -> list[list[str]]:
    header = ["包内编号", "材料名称", "拟证明事项", "原证据"]
    body = [
        [
            str(r.display_number),
            r.display_name,
            r.proof_purpose or "（未填写）",
            f"证据{r.evidence_number}" if r.evidence_number else "—",
        ]
        for r in rows
    ]
    return [header, *body]


def _appendix_lines(app: AppendixData) -> list[str]:
    lines = [
        GAP_APPENDIX_LEAD,
        f"分析生成时间：{app.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}（版本 v{app.version}）",
    ]
    if app.stale:
        lines.append("⚠ 分析之后案件证据已有更新，以下提示可能过期，建议重新运行材料缺口分析。")
    if not app.missing_items:
        lines.append("未发现材料完整性缺项。")
    for m in app.missing_items:
        desc = f"：{m['description']}" if m.get("description") else ""
        lines.append(f"· {m['title']}{desc}")
    return lines


def render_package_docx(data: PackageExportData) -> bytes:
    doc = DocxDocument()
    style = doc.styles["Normal"]
    style.font.name = "SimSun"
    style.font.size = Pt(10.5)

    doc.add_heading(f"材料包：{data.package.name}", level=1)
    doc.add_paragraph(f"案件：{data.case.name}")
    doc.add_paragraph(f"生成时间：{data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    doc.add_paragraph(DISCLAIMER)
    doc.add_paragraph()

    table = doc.add_table(rows=0, cols=4)
    table.style = "Table Grid"
    for i, row in enumerate(_package_index_rows(data.rows)):
        cells = table.add_row().cells
        for j, value in enumerate(row):
            cells[j].text = value
            if i == 0:
                for run in cells[j].paragraphs[0].runs:
                    run.bold = True

    for row in data.rows:
        doc.add_paragraph()
        doc.add_heading(f"材料{row.display_number}：{row.display_name}", level=2)
        doc.add_paragraph(f"拟证明事项：{row.proof_purpose or '（未填写）'}")
        doc.add_paragraph("原始内容：")
        block = data.contents.get(row.evidence_id) or ContentBlock(
            notes=["未取得原始内容。"]
        )
        for note in block.notes:
            p = doc.add_paragraph()
            run = p.add_run(f"【{note}】")
            run.bold = True
        for part in block.parts:
            if part.kind == "text":
                for line in part.text.splitlines():
                    if line.strip():
                        doc.add_paragraph(line)
            elif part.kind == "image" and part.image:
                try:
                    from docx.shared import Inches

                    doc.add_picture(io.BytesIO(part.image), width=Inches(5.8))
                except Exception as exc:
                    p = doc.add_paragraph()
                    run = p.add_run(f"【图片嵌入失败：{exc}，请查阅原始文件。】")
                    run.bold = True

    if data.appendix is not None:
        doc.add_paragraph()
        doc.add_heading(GAP_APPENDIX_TITLE, level=1)
        for line in _appendix_lines(data.appendix):
            doc.add_paragraph(line)

    for section in doc.sections:
        section.footer.paragraphs[0].text = DISCLAIMER

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _body_style(size: int = 10):
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle(
        name=f"body{size}",
        fontName=CJK_FONT,
        fontSize=size,
        leading=size * 1.6,
        wordWrap="CJK",
    )


def _note_style():
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle(
        name="origNote",
        fontName=CJK_FONT,
        fontSize=9,
        leading=14,
        wordWrap="CJK",
        backColor=colors.HexColor("#fff7ed"),
        textColor=colors.HexColor("#9a3412"),
        borderPadding=5,
    )


def _image_flowable(image: bytes, max_w: float, max_h: float):
    from PIL import Image as PILImage
    from reportlab.platypus import Image as RLImage

    w, h = PILImage.open(io.BytesIO(image)).size
    scale = min(max_w / w, max_h / h, 1.0) if w and h else 1.0
    return RLImage(io.BytesIO(image), width=w * scale, height=h * scale)


def render_package_pdf(data: PackageExportData) -> bytes:
    _ensure_cjk_font()
    buf = io.BytesIO()
    story: list = []
    body = _body_style()
    max_w, max_h = 170 * mm, 200 * mm

    story.append(Paragraph(f"材料包：{_escape(data.package.name)}", _heading_style(16)))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"案件：{_escape(data.case.name)}", body))
    story.append(
        Paragraph(f"生成时间：{data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", body)
    )
    story.append(Paragraph(DISCLAIMER, body))
    story.append(Spacer(1, 5 * mm))

    index_rows = [
        [Paragraph(_escape(str(c)), _heading_style(9)) for c in row]
        for row in _package_index_rows(data.rows)
    ]
    index = Table(index_rows, colWidths=[20 * mm, 50 * mm, 70 * mm, 28 * mm], repeatRows=1)
    index.setStyle(_table_style())
    story.append(index)

    for row in data.rows:
        story.append(PageBreak())
        story.append(
            Paragraph(_escape(f"材料{row.display_number}：{row.display_name}"), _heading_style(13))
        )
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(_escape(f"拟证明事项：{row.proof_purpose or '（未填写）'}"), body))
        story.append(Paragraph("原始内容：", body))
        block = data.contents.get(row.evidence_id) or ContentBlock(notes=["未取得原始内容。"])
        for note in block.notes:
            story.append(Paragraph(_escape(note), _note_style()))
            story.append(Spacer(1, 2 * mm))
        for part in block.parts:
            if part.kind == "text":
                # Split into paragraphs so long runs do not become one line block.
                for para in part.text.split("\n"):
                    if para.strip():
                        story.append(Paragraph(_escape(para), body))
            elif part.kind == "image" and part.image:
                try:
                    story.append(_image_flowable(part.image, max_w, max_h))
                    story.append(Spacer(1, 3 * mm))
                except Exception as exc:
                    story.append(
                        Paragraph(_escape(f"【图片嵌入失败：{exc}，请查阅原始文件。】"), _note_style())
                    )

    if data.appendix is not None:
        story.append(PageBreak())
        story.append(Paragraph(GAP_APPENDIX_TITLE, _heading_style(14)))
        story.append(Spacer(1, 4 * mm))
        for line in _appendix_lines(data.appendix):
            story.append(Paragraph(_escape(line), body))
            story.append(Spacer(1, 2 * mm))

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()


def _escape(text: str) -> str:
    """Escape ReportLab Paragraph metacharacters from user-supplied text."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_package_export(
    db: Session,
    case: Case,
    pkg: MaterialPackage,
    snapshot: MaterialPackageSnapshot,
    fmt: str,
    *,
    include_gap_appendix: bool = False,
    gap_result: CaseEvidenceGapResult | None = None,
) -> ExportJob:
    """Render a package volume strictly from one immutable snapshot."""
    if fmt not in PACKAGE_EXPORT_FORMATS:
        raise ExportError("UNSUPPORTED_FORMAT", f"不支持的材料包导出格式：{fmt}")

    rows = _rows_from_snapshot(snapshot)
    ev_ids = [r.evidence_id for r in rows]
    evidence_map = {
        e.id: e
        for e in (
            db.scalars(select(Evidence).where(Evidence.id.in_(ev_ids))).all()
            if ev_ids
            else []
        )
    }
    contents = build_contents(rows, evidence_map)
    appendix = build_appendix(db, gap_result) if (include_gap_appendix and gap_result) else None
    data = PackageExportData(
        case=case,
        package=pkg,
        rows=rows,
        contents=contents,
        generated_at=datetime.now(timezone.utc),
        appendix=appendix,
    )
    job = ExportJob(
        case_id=case.id,
        format=fmt,
        status=ExportStatus.RUNNING,
        package_id=pkg.id,
        snapshot_id=snapshot.id,
        snapshot_version=snapshot.version,
        include_gap_appendix=bool(include_gap_appendix),
        gap_result_id=gap_result.id if gap_result is not None else None,
    )
    render = render_package_docx if fmt == "docx" else render_package_pdf
    return _run_job(db, job, lambda: render(data))
