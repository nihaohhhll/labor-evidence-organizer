"""HTTP header helpers.

Filenames for evidence exports are Chinese, and HTTP header values must be
latin-1 encodable. `Content-Disposition` therefore carries both an ASCII
fallback and an RFC 5987 `filename*` parameter, which is how every modern
browser recovers the real name.
"""

from __future__ import annotations

from urllib.parse import quote

# Leading/trailing junk stripped from the ASCII stem, e.g. the `-` left behind
# when every CJK character of `材料包-仲裁材料包.pdf` is dropped.
_FALLBACK_TRIM = " .-_"


def _ascii_fallback(filename: str) -> str:
    """Best-effort printable-ASCII name for clients that ignore `filename*`.

    Dropping non-ASCII characters alone degrades Chinese names to shells like
    `-.pdf`, and leaves quoted-string metacharacters (`"`, `;`, `/`) that break
    naive header parsers. This keeps whatever sane ASCII remains, neutralises
    the dangerous characters, and guarantees a real stem so the result is
    always a usable, non-empty name.
    """
    name = "".join(ch for ch in filename if ch.isascii() and ch.isprintable())
    # Quoted-string must not contain `"` or `\`; `/` and `;` are neutralised
    # because legacy clients split paths/parameters on them.
    name = name.replace('"', "").replace("\\", "")
    name = name.replace("/", "_").replace(";", "_").strip()
    if not name:
        return "download"
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = stem.strip(_FALLBACK_TRIM)
    if not any(ch.isalnum() for ch in stem):
        # `-.pdf` / `材料包.pdf`-style shells get a generic but real stem.
        stem = "download"
    ext = ext.strip(_FALLBACK_TRIM)
    return f"{stem}.{ext}" if ext else stem


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """Build a `Content-Disposition` value safe for non-ASCII filenames.

    The ASCII fallback keeps older clients working; `filename*` carries the
    exact UTF-8 name per RFC 5987.
    """
    disposition = "inline" if inline else "attachment"
    ascii_fallback = _ascii_fallback(filename)
    # Percent-encode anything outside printable ASCII so the header itself
    # always encodes to latin-1.
    encoded = quote(filename, safe="")
    return f'{disposition}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def nosniff_private_headers(filename: str, *, inline: bool = False) -> dict[str, str]:
    """Headers shared by every download: no sniffing, no shared caching."""
    return {
        "Content-Disposition": content_disposition(filename, inline=inline),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
