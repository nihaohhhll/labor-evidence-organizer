"""Sensitive-data redaction for logs (docs/11_SECURITY.md §9, §不应该做).

Evidence material routinely contains 身份证号, 银行卡号, 手机号 and email.
None of those may ever reach a log line, an error message or an analytics
event. `redact()` is the single chokepoint: anything user-derived that gets
logged must pass through it first.

Design notes
------------
* Patterns are deliberately anchored to the *surrounding context* where the
  format allows (e.g. 身份证 followed by 号码/ID), because bare 6-18 digit
  numbers are far too common in ordinary evidence text to blank blindly.
* Replacement keeps a short masked form (last 2-4 characters) so support can
  still correlate two log lines about the same subject without learning the
  full value.
"""

from __future__ import annotations

import re

MASK = "***REDACTED***"

# (compiled pattern, replacement) applied in order.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # 18-digit PRC ID, optionally followed by the digit that encodes gender.
    (re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)"), lambda m: _mask_tail(m.group(1), 4)),
    # 15-digit legacy ID.
    (re.compile(r"(?<!\d)(\d{15})(?!\d)"), lambda m: _mask_tail(m.group(1), 4)),
    # Bank card: 16-19 digits, possibly separated by spaces or dashes.
    (
        re.compile(r"(?<!\d)((?:\d[ -]?){15,18}\d)(?!\d)"),
        lambda m: _mask_tail(m.group(1).replace(" ", "").replace("-", ""), 4),
    ),
    # Mainland mobile number: 11 digits starting 1[3-9], optionally written
    # with a +86 prefix and single spaces/dashes between digits.
    #
    # The whole number must be captured, not just the 3-digit prefix — a
    # 3-digit capture leaves the remaining 8 digits adjacent, which fails the
    # trailing lookbehind and masks nothing at all. Separators are allowed
    # inside the number because 「138-0013-8000」 and 「138 0013 8000」 are how
    # people actually write them in evidence material.
    (
        re.compile(r"(?:(?<!\d)\+?86[ -]?)?(?<!\d)(1[3-9](?:[ -]?\d){9})(?!\d)"),
        lambda m: _mask_mobile(m.group(1)),
    ),
    # Email: mask the local part, keep the domain for correlation.
    (
        re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})"),
        lambda m: f"{m.group(1)[0]}***@{m.group(2)}",
    ),
    # JWT bearer tokens.
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"), MASK),
    # API keys commonly prefixed this way.
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9]{16,}"), MASK),
    # Authorization headers of any scheme.
    (re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(\S+)"), r"\1" + MASK),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._-]{12,})"), r"\1" + MASK),
)


def _mask_tail(value: str, keep: int) -> str:
    """Keep the last `keep` characters, mask the rest."""
    if len(value) <= keep:
        return MASK
    return "*" * (len(value) - keep) + value[-keep:]


def _mask_mobile(raw: str) -> str:
    """Mask a mobile number, dropping any spaces/dashes it was written with."""
    digits = re.sub(r"[ -]", "", raw)
    if len(digits) < 7:  # pragma: no cover - pattern guarantees 11
        return MASK
    return f"{digits[:3]}****{digits[-4:]}"


def redact(text: str) -> str:
    """Return `text` with every recognised sensitive value masked.

    Never raises: redaction runs on the logging path, where an exception would
    either lose the log or, worse, surface the unmasked original.
    """
    if not text:
        return text
    try:
        result = text
        for pattern, repl in _PATTERNS:
            result = pattern.sub(repl, result)
        return result
    except Exception:  # pragma: no cover - defensive
        return MASK


def redact_mapping(data: dict) -> dict:
    """Recursively redact string values inside a JSON-able mapping."""
    out: dict = {}
    for key, value in data.items():
        if isinstance(value, str):
            out[key] = redact(value)
        elif isinstance(value, dict):
            out[key] = redact_mapping(value)
        elif isinstance(value, list):
            out[key] = [
                redact_mapping(v) if isinstance(v, dict) else redact(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            out[key] = value
    return out
