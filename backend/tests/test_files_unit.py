"""Phase 2 unit tests: validation and storage guards (no HTTP)."""

from __future__ import annotations

import pytest

from app.files.validation import (
    UnsupportedFileType,
    detect_mime,
    extension_of,
    validate_upload,
)
from app.storage import LocalStorage, sha256_hex
from tests.helpers import make_png, make_txt


def test_extension_of_handles_missing_and_uppercase():
    assert extension_of("a.PNG") == ".png"
    assert extension_of("archive.tar.gz") == ".gz"
    assert extension_of("noext") == ""


def test_detect_mime_reads_magic_bytes():
    assert detect_mime(make_png()) == "image/png"
    assert detect_mime(b"%PDF-1.4 ...") == "application/pdf"


def test_validate_accepts_supported_types():
    assert validate_upload("a.txt", make_txt()) == "text/plain"
    assert validate_upload("a.png", make_png()) == "image/png"


def test_validate_rejects_empty_name_and_empty_body():
    with pytest.raises(UnsupportedFileType):
        validate_upload("   ", make_txt())
    with pytest.raises(UnsupportedFileType):
        validate_upload("a.txt", b"")


def test_validate_rejects_unknown_extension():
    with pytest.raises(UnsupportedFileType) as exc:
        validate_upload("payload.exe", b"MZ\x90\x00")
    assert "不支持的文件类型" in str(exc.value)


def test_validate_rejects_content_extension_mismatch():
    """Renaming a PDF to .png must be rejected (mime attack)."""
    with pytest.raises(UnsupportedFileType):
        validate_upload("fake.png", b"%PDF-1.4 not a png")


def test_validate_rejects_oversized_file():
    with pytest.raises(UnsupportedFileType) as exc:
        validate_upload("big.txt", make_txt("x" * 5000), max_bytes=100)
    assert "大小上限" in str(exc.value)


def test_text_plain_requires_valid_utf8():
    with pytest.raises(UnsupportedFileType):
        validate_upload("bad.txt", b"\xff\xfe\x00\x01binary garbage")


def test_local_storage_roundtrip(tmp_path):
    store = LocalStorage(str(tmp_path))
    obj = store.put("cases/x/originals/abc.txt", b"hello")
    assert obj.sha256 == sha256_hex(b"hello")
    assert store.get("cases/x/originals/abc.txt") == b"hello"
    assert store.exists("cases/x/originals/abc.txt")


def test_local_storage_refuses_to_overwrite_immutable_object(tmp_path):
    store = LocalStorage(str(tmp_path))
    store.put("k.txt", b"original")
    with pytest.raises(FileExistsError):
        store.put("k.txt", b"different bytes")
    # Writing identical bytes is a no-op, not an error.
    assert store.put("k.txt", b"original").sha256 == sha256_hex(b"original")


def test_local_storage_blocks_path_traversal(tmp_path):
    store = LocalStorage(str(tmp_path))
    with pytest.raises(ValueError):
        store.put("../../etc/passwd", b"pwned")
    with pytest.raises(ValueError):
        store.put("/absolute/path.txt", b"pwned")
    assert store.exists("../escape.txt") is False
