"""Logging configuration with built-in redaction.

`basicConfig` alone would let a future `logger.info("user %s", id_number)`
leak a 身份证号 straight to disk. Installing a redacting *filter* on the root
logger means every record — from any module, at any level — is scrubbed
before it is formatted, which is the only arrangement that stays safe as the
codebase grows.

docs/11_SECURITY.md §9: 日志脱敏.
"""

from __future__ import annotations

import logging
import sys

from app.redaction import redact

# Record attributes that carry free-form text and therefore need scrubbing.
_TEXT_ATTRS = ("message", "asctime", "exc_text", "args")


class RedactingFilter(logging.Filter):
    """Scrub sensitive values out of every log record, in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # The formatted message is what actually reaches the output, so
            # scrub both it and the raw args (a handler may re-format).
            record.msg = redact(str(record.msg))
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: redact(str(v)) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        redact(str(a)) if isinstance(a, str) else a for a in record.args
                    )
            if record.exc_text:
                record.exc_text = redact(record.exc_text)
        except Exception:  # pragma: no cover - never lose a log to redaction
            record.msg = "***REDACTED***"
        return True


def install_redaction(logger: logging.Logger | None = None) -> None:
    """Attach the redacting filter to `logger` and all of its handlers."""
    target = logger or logging.getLogger()
    # Guard against double-install when tests reload the module.
    if any(isinstance(f, RedactingFilter) for f in target.filters):
        return
    target.addFilter(RedactingFilter())
    for handler in target.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())


def configure_logging(level: int = logging.INFO) -> None:
    """One-call setup used by `app.main`."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
        force=True,
    )
    install_redaction()
