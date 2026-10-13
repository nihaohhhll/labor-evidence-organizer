"""ORM models package.

Importing this module registers every table on the declarative base, which
Alembic and `create_all()` rely on.
"""

from app.models.analysis import DocumentAnalysis
from app.models.audit import AuditLog
from app.models.base import SoftDeleteMixin, TimestampMixin, utcnow
from app.models.case import Case, CaseStatus
from app.models.case_gap import CaseEvidenceGapResult
from app.models.claim import Claim
from app.models.event import Event
from app.models.export import ExportFormat, ExportJob, ExportStatus
from app.models.evidence import (
    Evidence,
    EvidenceClaim,
    EvidenceEvent,
    EvidencePerson,
    Person,
    ReviewStatus,
)
from app.models.file import File, FileStatus
from app.models.material_package import (
    ItemReviewStatus,
    MaterialPackage,
    MaterialPackageItem,
    MaterialPackageSnapshot,
    PackageStatus,
)
from app.models.review import ReviewItem, ReviewStatusValue
from app.models.user import User

__all__ = [
    "AuditLog",
    "Case",
    "CaseEvidenceGapResult",
    "CaseStatus",
    "Claim",
    "DocumentAnalysis",
    "Event",
    "Evidence",
    "EvidenceClaim",
    "EvidenceEvent",
    "EvidencePerson",
    "ExportFormat",
    "ExportJob",
    "ExportStatus",
    "File",
    "FileStatus",
    "ItemReviewStatus",
    "MaterialPackage",
    "MaterialPackageItem",
    "MaterialPackageSnapshot",
    "PackageStatus",
    "Person",
    "ReviewItem",
    "ReviewStatus",
    "ReviewStatusValue",
    "SoftDeleteMixin",
    "TimestampMixin",
    "User",
    "utcnow",
]
