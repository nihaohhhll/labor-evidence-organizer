"""AI and OCR provider abstractions.

Business code depends on these protocols only — never on a vendor SDK
(docs/04_TECH_ARCHITECTURE.md). Every implementation must be able to record
`provider`, `model` and `prompt_version` so results stay attributable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class DocumentInput:
    """What a provider receives: the filename, its bytes and derived text."""

    filename: str
    mime_type: str
    data: bytes
    extracted_text: str = ""


@dataclass
class DocumentAnalysisResult:
    """Structured AI output.

    Every field is allowed to be null: "not found in the material" is an
    honest answer, and inventing a value would violate docs/08_PROMPT_SPEC.
    """

    document_type: str = "other"
    type_confidence: float = 0.0
    type_reason: str = ""
    raw_text: str = ""
    dates: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    persons: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    proof_purpose: str = ""
    confidence: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"
    prompt_version: str = "unknown"


@dataclass
class OCRResult:
    text: str = ""
    confidence: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"


@runtime_checkable
class AIProvider(Protocol):
    """Structured analysis of one document."""

    name: str
    model: str
    prompt_version: str

    async def analyze_document(self, document: DocumentInput) -> DocumentAnalysisResult: ...


@runtime_checkable
class OCRProvider(Protocol):
    """Text extraction from images (and from PDF pages with no text layer)."""

    name: str
    model: str

    async def extract(self, document: DocumentInput) -> OCRResult: ...


class ProviderNotFound(LookupError):
    """Raised when a configured provider name has no implementation."""
