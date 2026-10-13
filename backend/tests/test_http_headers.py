"""`Content-Disposition` header construction (download filename compatibility).

Chinese export names must reach modern browsers exactly (via RFC 5987
`filename*`) while legacy clients that read only `filename` still get a
reasonable, non-empty, header-safe ASCII fallback.
"""

from __future__ import annotations

import re

import pytest

from app.http_headers import content_disposition, nosniff_private_headers


def _fallback(header: str) -> str:
    m = re.search(r'filename="([^"]*)"', header)
    assert m, header
    return m.group(1)


def _filename_star(header: str) -> str:
    from urllib.parse import unquote

    m = re.search(r"filename\*=UTF-8''(\S+)", header)
    assert m, header
    return unquote(m.group(1))


@pytest.mark.parametrize(
    "filename,expected_fallback",
    [
        # Chinese name: the old encode("ascii","ignore") fallback was "-.pdf".
        ("材料包-仲裁材料包.pdf", "download.pdf"),
        # English + spaces survive verbatim.
        ("材料包-March Bundle v2.docx", "March Bundle v2.docx"),
        # Parameter separator neutralised, not passed through raw.
        ("材料包-Q1;草案.pdf", "Q1.pdf"),
        # Quoted-string metacharacter removed (would terminate the quotes).
        ('材料包-a"b.txt', "ab.txt"),
        # Path separators neutralised even without _safe_filename.
        ("../secret.pdf", "secret.pdf"),
        # Pure Chinese, no extension: generic but real stem.
        ("纯中文", "download"),
        # Degenerate stem from a fully-sanitised traversal case name.
        ("证据包-....etcpasswd.pdf", "etcpasswd.pdf"),
        # ASCII-only names pass through untouched.
        ("evidence.csv", "evidence.csv"),
    ],
)
def test_ascii_fallback_is_non_empty_and_reasonable(filename, expected_fallback):
    header = content_disposition(filename)
    fallback = _fallback(header)
    assert fallback == expected_fallback
    # Header must be latin-1 encodable (hard HTTP requirement).
    header.encode("latin-1")
    assert fallback.isascii() and fallback.strip()


def test_filename_star_carries_exact_utf8_name():
    header = content_disposition("材料包-仲裁材料包（第一版）.pdf")
    assert _filename_star(header) == "材料包-仲裁材料包（第一版）.pdf"
    assert header.startswith("attachment;")
    assert header.encode("latin-1")


def test_crlf_injection_never_reaches_header():
    header = content_disposition("evil\r\nX-Injected: 1.pdf")
    assert "\r" not in header and "\n" not in header
    header.encode("latin-1")


def test_no_traversal_in_header():
    header = content_disposition("../../etc/passwd")
    assert "../" not in header
    assert "/" not in _fallback(header)


def test_inline_variant_keeps_filename_params():
    header = content_disposition("材料包-卷.pdf", inline=True)
    assert header.startswith("inline;")
    assert _filename_star(header) == "材料包-卷.pdf"


def test_nosniff_private_headers_shape():
    headers = nosniff_private_headers("材料包-卷.pdf")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "private, no-store"
    assert headers["Content-Disposition"].startswith("attachment;")
    headers["Content-Disposition"].encode("latin-1")
