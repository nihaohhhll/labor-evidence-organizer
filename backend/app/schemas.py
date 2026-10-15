"""Pydantic request/response schemas for auth and cases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from datetime import date, time

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

EMAIL_MAX = 320
NAME_MAX = 200
PASSWORD_MIN = 12
PASSWORD_MAX = 128

# Password policy follows NIST SP 800-63B rather than legacy composition
# rules. The standard explicitly advises *against* requiring uppercase +
# digits + symbols: users satisfy such rules with predictable mutations
# ("Password1!"), which are weaker than an unstructured passphrase of the
# same length. What actually resists attack is length plus not appearing in
# a breach corpus.
#
# So the rules here are: long enough, not a known-bad password, no keyboard
# runs, no single repeated character, no leading/trailing whitespace.

# Passwords that appear at the top of every breach corpus, normalised to
# lowercase. Rejected outright regardless of length.
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "password1234",
        "12345678",
        "123456789",
        "1234567890",
        "12345678901",
        "qwertyuiop",
        "qwerty123456",
        "letmein123",
        "iloveyou123",
        "admin123456",
        "administrator",
        "passw0rd123",
        "welcome1234",
        "abc123456789",
        "zaq12wsxcde3",
        "1qaz2wsx3edc",
    }
)

# Long runs of adjacent keys or ascending digits: cheap for an attacker to
# generate, and users reach for them when a rule only checks length.
_SEQUENCE_RE = re.compile(
    r"(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|"
    r"stu|tuv|uvw|vwx|wxy|xyz|012|123|234|345|456|567|678|789|890|"
    r"qwe|wer|ert|rty|tyu|yui|uio|iop|asd|sdf|dfg|fgh|ghj|hjk|jkl)",
    re.IGNORECASE,
)


def password_problems(value: str) -> list[str]:
    """Return every reason `value` is an unacceptable password.

    Collecting all problems at once beats failing on the first: the user
    fixes them in one pass instead of discovering them one submit at a time.
    """
    problems: list[str] = []
    if len(value) < PASSWORD_MIN:
        problems.append(f"密码至少需要 {PASSWORD_MIN} 位")
    if len(value) > PASSWORD_MAX:
        problems.append(f"密码不能超过 {PASSWORD_MAX} 位")
    if value.strip() != value or not value.strip():
        problems.append("密码不能包含首尾空白")
    if value.lower() in COMMON_PASSWORDS:
        problems.append("该密码过于常见，请更换")
    if _SEQUENCE_RE.search(value.lower()):
        problems.append("密码不能包含连续的键盘或数字序列")
    if value and len(set(value)) < 5:
        problems.append("密码使用字符过少")
    return problems


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------


class RegisterIn(BaseModel):
    email: EmailStr = Field(max_length=EMAIL_MAX)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _check_password_strength(cls, v: str) -> str:
        problems = password_problems(v)
        if problems:
            # pydantic joins ValueError args into one message; keep them
            # separated so the user can act on every rule at once.
            raise ValueError("；".join(problems))
        return v


class LoginIn(BaseModel):
    email: EmailStr = Field(max_length=EMAIL_MAX)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None = None
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------- cases ----------


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("case name must not be blank")
        return v


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=NAME_MAX)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("case name must not be blank")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {"ACTIVE", "ARCHIVED", "CLOSED"}
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v


class CaseOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class CaseDetailOut(CaseOut):
    file_count: int = 0
    evidence_count: int = 0
    event_count: int = 0


class CaseNarrativeOut(BaseModel):
    """AI draft only — the client saves it via PATCH /cases/{id}."""

    narrative: str = Field(min_length=1, max_length=5000)
    provider: str
    model: str


class Page(BaseModel):
    items: list[CaseOut]
    total: int
    limit: int
    offset: int


# ---------- files ----------


class FileDetailOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    original_filename: str
    mime_type: str
    size: int
    sha256: str
    status: str
    error_message: str | None = None
    created_at: datetime
    download_url: str = ""


class FileListOut(BaseModel):
    files: list[FileDetailOut]
    status_counts: dict[str, int] = Field(default_factory=dict)


class SkippedFile(BaseModel):
    filename: str
    reason: str


class UploadOutcomeOut(BaseModel):
    """Batch upload result: one bad file must not abort the batch."""

    files: list[FileDetailOut]
    skipped: list[SkippedFile] = Field(default_factory=list)


# ---------- analysis ----------


class AnalysisOut(ORMModel):
    id: uuid.UUID
    file_id: uuid.UUID
    provider: str
    model: str
    prompt_version: str
    classification: str | None = None
    classification_reason: str | None = None
    confidence: float | None = None
    raw_text: str | None = None
    created_at: datetime
    # Structured projections lifted out of `structured_json`.
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    persons: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    summary: str | None = None
    proof_purpose: str | None = None


class AnalysisTriggerOut(BaseModel):
    analyzed: int
    failed: int = 0


# ---------- evidence ----------


class EvidenceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: str = Field(default="other", max_length=64)
    event_date: date | None = None
    summary: str | None = Field(default=None, max_length=4000)
    proof_purpose: str | None = Field(default=None, max_length=4000)
    source_file_id: uuid.UUID | None = None
    confirm_now: bool = False

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("证据名称不能为空")
        return v


class EvidenceUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=64)
    event_date: date | None = None
    summary: str | None = Field(default=None, max_length=4000)
    proof_purpose: str | None = Field(default=None, max_length=4000)


class EvidenceDetailOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    source_file_id: uuid.UUID | None = None
    evidence_number: int
    title: str
    category: str
    event_date: date | None = None
    summary: str | None = None
    proof_purpose: str | None = None
    confidence: float | None = None
    review_status: str
    # The column is nullable JSON; normalise None to an empty list so callers
    # never have to branch on nullability.
    user_edited_fields: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("user_edited_fields", mode="before")
    @classmethod
    def _none_to_list(cls, v):
        return v or []


class EvidenceListOut(BaseModel):
    evidence: list[EvidenceDetailOut]
    total: int


class EvidenceConfirmOut(BaseModel):
    id: uuid.UUID
    review_status: str


# ---------- review ----------


class ReviewItemOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    field_name: str
    ai_value: dict | None = None
    user_value: dict | None = None
    status: str
    confidence: float | None = None


class ReviewListOut(BaseModel):
    items: list[ReviewItemOut]
    total: int


class ReviewResolveIn(BaseModel):
    user_value: dict | None = None


class ReviewResolvedOut(BaseModel):
    id: uuid.UUID
    status: str
    applied: dict = Field(default_factory=dict)


# ---------- timeline ----------


class EventCreate(BaseModel):
    event_date: date | None = None
    event_time: time | None = None
    precision: str = "day"
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("precision")
    @classmethod
    def _valid_precision(cls, v: str) -> str:
        allowed = {"day", "month", "unknown"}
        if v not in allowed:
            raise ValueError(f"precision must be one of {sorted(allowed)}")
        return v


class EventUpdate(BaseModel):
    event_date: date | None = None
    event_time: time | None = None
    precision: str | None = None
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    review_status: str | None = None

    @field_validator("precision")
    @classmethod
    def _valid_precision(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {"day", "month", "unknown"}
        if v not in allowed:
            raise ValueError(f"precision must be one of {sorted(allowed)}")
        return v


class EventDetailOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    event_date: date | None = None
    event_time: time | None = None
    precision: str
    title: str
    description: str | None = None
    confidence: float | None = None
    review_status: str
    created_at: datetime


class EventListOut(BaseModel):
    events: list[EventDetailOut]
    total: int


class EventMergeIn(BaseModel):
    event_ids: list[uuid.UUID] = Field(min_length=2)
    title: str | None = Field(default=None, max_length=300)


# ---------- evidence gaps (A3) ----------


class GapSource(BaseModel):
    kind: str
    id: uuid.UUID
    excerpt: str | None = None


class MissingItem(BaseModel):
    code: str
    title: str
    description: str
    related_fact_ids: list[uuid.UUID] = Field(default_factory=list)
    suggested_evidence_types: list[str] = Field(default_factory=list)
    priority: str = "medium"
    gap_id: str | None = None
    sources: list[GapSource] = Field(default_factory=list)
    check_basis: dict | None = None


class GapJson(BaseModel):
    missing_items: list[MissingItem] = Field(default_factory=list)


class EvidenceGapResultOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    status: str
    gap_json: dict | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime


class EvidenceGapTriggerOut(BaseModel):
    version: int | None = None
    status: str


class EvidenceGapHistoryOut(BaseModel):
    results: list[EvidenceGapResultOut]
    total: int


# ---------- export ----------


class ExportCreateIn(BaseModel):
    format: str = Field(pattern="^(?i)(docx|pdf|zip)$")


class ExportJobOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    format: str
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    # Phase 9-C: material package binding (optional — case exports leave them null)
    package_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None
    snapshot_version: int | None = None
    include_gap_appendix: bool = False
    gap_result_id: uuid.UUID | None = None


class ExportListOut(BaseModel):
    exports: list[ExportJobOut]
    total: int


# ---------- material packages (Phase 9-A) ----------


class MaterialPackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("材料包名称不能为空")
        return v


class MaterialPackageUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] | None = None


class MaterialPackageItemIn(BaseModel):
    evidence_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=300)
    proof_purpose: str | None = Field(default=None, max_length=4000)
    review_status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None


class MaterialPackageItemsSaveIn(BaseModel):
    expected_draft_version: int = Field(ge=1)
    items: list[MaterialPackageItemIn] = Field(default_factory=list)


class MaterialPackageItemOut(BaseModel):
    id: uuid.UUID
    evidence_id: uuid.UUID
    evidence_number: int | None = None
    source_file_id: uuid.UUID | None = None
    item_order: int
    display_number: int
    display_name: str
    proof_purpose: str | None = None
    review_status: str
    created_at: datetime
    updated_at: datetime


class MaterialPackageOut(ORMModel):
    id: uuid.UUID
    case_id: uuid.UUID
    name: str
    status: str
    draft_version: int
    item_count: int = 0
    snapshot_count: int = 0
    created_at: datetime
    updated_at: datetime


class MaterialPackageDetailOut(MaterialPackageOut):
    items: list[MaterialPackageItemOut] = Field(default_factory=list)


class MaterialPackageListOut(BaseModel):
    items: list[MaterialPackageOut]
    total: int
    limit: int
    offset: int


class MaterialPackageSnapshotCreateIn(BaseModel):
    expected_draft_version: int = Field(ge=1)


class MaterialPackageSnapshotOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    version: int
    draft_version_captured: int
    created_at: datetime
    content: dict


class MaterialPackageSnapshotListOut(BaseModel):
    snapshots: list[MaterialPackageSnapshotOut]
    total: int


class MaterialPackageExportIn(BaseModel):
    # No format pattern here: an unsupported value must surface as the
    # project envelope 422 UNSUPPORTED_FORMAT (service-raised), not a
    # FastAPI validation error (decision 4.2: docx/pdf only).
    format: str = Field(min_length=1, max_length=16)
    snapshot_version: int | None = Field(default=None, ge=1)
    include_gap_appendix: bool = False
