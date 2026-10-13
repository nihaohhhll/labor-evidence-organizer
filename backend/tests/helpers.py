"""Shared test fixtures: valid sample documents for every accepted format.

Building them here (rather than committing binaries) keeps the fixtures
readable and guarantees the magic-byte signatures line up with validation.
"""

from __future__ import annotations

import io
import zipfile

SAMPLE_TEXT = """劳动合同

甲方：某某科技有限公司
乙方：张三

一、合同期限
本合同期限自2022年10月1日起至2025年9月30日止，其中试用期3个月。

二、劳动报酬
乙方月工资为7500元，每月15日以银行转账方式发放。

三、工作内容
乙方担任软件工程师岗位。
"""


def make_txt(content: str = SAMPLE_TEXT) -> bytes:
    return content.encode("utf-8")


def make_png() -> bytes:
    """A minimal but structurally valid 1x1 PNG."""
    import base64

    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        b"z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def make_jpeg() -> bytes:
    """A minimal JPEG: SOI + APP0/JFIF header + EOI."""
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000"
        "ffdb004300ffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "ffc0000b080001000101011100ffc4001f000001050101010101010000000000"
        "0000000102030405060708090a0bffc400b51000020103030204030505040400"
        "00017d01020300041105122131410613516107227114328191a1082342b1c115"
        "52d1f02433627282090a161718191a25262728292a3435363738393a43444546"
        "4748494a535455565758595a636465666768696a737475767778797a83848586"
        "8788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2"
        "c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5"
        "f6f7f8f9faffda0008010100003f00f9fe8a28a2803fffd9"
    )


def make_pdf(text: str = SAMPLE_TEXT) -> bytes:
    """A real single-page PDF with an extractable CJK text layer.

    A CJK-capable font must be embedded explicitly: PyMuPDF's default
    (Helvetica) cannot render Chinese and silently emits dots instead of
    glyphs, which would make this fixture useless for extraction tests.
    WenQuanYi Zen Hei is preferred because it ships with the CJK coverage
    these tests need.
    """
    import os

    import pymupdf

    candidates = (
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    font_path = next((p for p in candidates if os.path.exists(p)), None)

    doc = pymupdf.open()
    page = doc.new_page()
    if font_path:
        page.insert_font(fontname="F0", fontfile=font_path)
        page.insert_text((50, 72), text, fontsize=9, fontname="F0")
    else:  # pragma: no cover - only when the container has no fonts at all
        page.insert_text((50, 72), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def make_docx(text: str = SAMPLE_TEXT) -> bytes:
    """A real DOCX with paragraphs and one table."""
    import docx

    doc = docx.Document()
    for line in text.strip().splitlines():
        if line.strip():
            doc.add_paragraph(line.strip())
    table = doc.add_row = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "月份"
    table.rows[0].cells[1].text = "应发工资7500元"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_zip_with_docx() -> bytes:
    """A zip is not an accepted upload type; used for negative tests."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "hello")
    return buf.getvalue()


def upload(client, headers, case_id: str, filename: str, data: bytes):
    """POST one file as multipart and return the response."""
    return client.post(
        f"/api/v1/cases/{case_id}/files",
        files=[( "files", (filename, data, "application/octet-stream"))],
        headers=headers,
    )
