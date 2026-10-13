"""MIME / extension validation and content sniffing.

Extension and MIME must both be on the whitelist (docs/11_SECURITY.md §7);
a renamed file must not slip through.
"""

from __future__ import annotations

try:  # libmagic is optional; signatures below already cover every accepted type.
    import magic  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only without libmagic
    magic = None  # type: ignore[assignment]

from app.config import settings

# Canonical extension per allowed MIME type.
MIME_TO_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "application/pdf": (".pdf",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
    "text/plain": (".txt",),
}

# Magic-bytes signatures for the formats we accept. Used as a second check
# on top of python-mime so an attacker cannot rename a shell script to .png.
_SIGNATURES: dict[str, tuple[bytes, int]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n", 0),
    "image/jpeg": (b"\xff\xd8\xff", 0),
    "application/pdf": (b"%PDF-", 0),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        b"PK\x03\x04",
        0,
    ),
}


class UnsupportedFileType(ValueError):
    """Raised when a file fails the whitelist or signature check."""


def extension_of(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot > 0 else ""


def detect_mime(data: bytes) -> str:
    """Best-effort content type from magic bytes, falling back to mime lib."""
    for mime, (sig, offset) in _SIGNATURES.items():
        if data[offset : offset + len(sig)] == sig:
            return mime
    if magic is None:  # pragma: no cover - only when libmagic is absent
        return "application/octet-stream"
    try:
        return magic.from_buffer(data[:2048], mime=True) or "application/octet-stream"
    except Exception:  # pragma: no cover
        return "application/octet-stream"


def _signature_matches(mime: str, data: bytes) -> bool:
    """True when the bytes carry the signature for `mime`.

    `text/plain` has no fixed signature, so it only needs to be valid UTF-8.
    """
    if mime == "text/plain":
        try:
            data[:4096].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    sig = _SIGNATURES.get(mime)
    if sig is None:  # pragma: no cover - unknown mime
        return False
    signature, offset = sig
    return data[offset : offset + len(signature)] == signature


def validate_upload(filename: str, data: bytes, max_bytes: int | None = None) -> str:
    """Validate an upload and return the canonical MIME type.

    Raises `UnsupportedFileType` with a user-safe message on any failure.
    """
    limit = max_bytes if max_bytes is not None else settings.max_upload_bytes
    if not filename or not filename.strip():
        raise UnsupportedFileType("文件名不能为空。")
    if not data:
        raise UnsupportedFileType("文件内容为空。")
    if len(data) > limit:
        raise UnsupportedFileType(f"文件超过大小上限（{limit // (1024 * 1024)} MB）。")

    ext = extension_of(filename)
    detected = detect_mime(data)

    # Extension must map to an allowed MIME, and content must match it.
    allowed_exts = {
        e: m for m, exts in MIME_TO_EXTENSIONS.items() for e in exts if m in settings.allowed_mime_set
    }
    expected = allowed_exts.get(ext)
    if expected is None:
        raise UnsupportedFileType(f"不支持的文件类型：{ext or '（无扩展名）'}。")

    if detected != expected:
        # A .png whose bytes are a PDF is a rename attack; reject it.
        raise UnsupportedFileType("文件内容与扩展名不一致。")
    if not _signature_matches(expected, data):
        raise UnsupportedFileType("文件内容无法识别。")

    return expected
