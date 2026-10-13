"""Material package service (Phase 9-A).

Every business rule for packages lives here so the routes stay thin:

* ownership is always resolved through the owning case (404 semantics);
* an item may only reference evidence that exists in the same case —
  a non-existent id and a cross-case id fail identically so the API never
  confirms whether a guessed id exists anywhere;
* item ordering/numbering is assigned from the payload position, never from
  database row order;
* draft saves use an optimistic lock (`draft_version`) so a later save can
  never silently overwrite an earlier one;
* snapshots are append-only and fully self-contained (rule 7: a snapshot
  whose source evidence vanished or changed reports the anomaly instead of
  pretending to be healthy).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.case import Case
from app.models.evidence import Evidence
from app.models.material_package import (
    ItemReviewStatus,
    MaterialPackage,
    MaterialPackageItem,
    MaterialPackageSnapshot,
    PackageStatus,
)

_MAX_ITEMS_PER_PACKAGE = 200
_NAME_MAX = 200
_DISPLAY_NAME_MAX = 300
_PROOF_PURPOSE_MAX = 4000


class MaterialPackageServiceError(Exception):
    """Business error carrying a safe code + message and an HTTP status."""

    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class ItemInput:
    """One item from the client payload."""

    evidence_id: uuid.UUID
    display_name: str | None = None
    proof_purpose: str | None = None
    review_status: str | None = None


# ---------- ownership ----------


def get_owned_case(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> Case:
    case = db.scalar(
        select(Case).where(
            Case.id == case_id, Case.user_id == user_id, Case.deleted_at.is_(None)
        )
    )
    if case is None:
        raise MaterialPackageServiceError("CASE_NOT_FOUND", "Case not found.", 404)
    return case


def get_owned_package(
    db: Session, package_id: uuid.UUID, user_id: uuid.UUID
) -> MaterialPackage:
    """Resolve a package through its case so ownership is always checked."""
    pkg = db.scalar(
        select(MaterialPackage)
        .join(Case, Case.id == MaterialPackage.case_id)
        .where(
            MaterialPackage.id == package_id,
            Case.user_id == user_id,
            Case.deleted_at.is_(None),
        )
    )
    if pkg is None:
        raise MaterialPackageServiceError(
            "PACKAGE_NOT_FOUND", "Material package not found.", 404
        )
    return pkg


# ---------- draft package CRUD ----------


def create_package(
    db: Session, case_id: uuid.UUID, user_id: uuid.UUID, name: str
) -> MaterialPackage:
    name = (name or "").strip()
    if not name:
        raise MaterialPackageServiceError("INVALID_NAME", "材料包名称不能为空")
    if len(name) > _NAME_MAX:
        raise MaterialPackageServiceError("INVALID_NAME", f"材料包名称不能超过 {_NAME_MAX} 字")
    pkg = MaterialPackage(case_id=case_id, name=name, created_by=user_id)
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


def update_package(
    db: Session,
    pkg: MaterialPackage,
    *,
    name: str | None = None,
    status: str | None = None,
) -> MaterialPackage:
    if name is not None:
        name = name.strip()
        if not name:
            raise MaterialPackageServiceError("INVALID_NAME", "材料包名称不能为空")
        if len(name) > _NAME_MAX:
            raise MaterialPackageServiceError(
                "INVALID_NAME", f"材料包名称不能超过 {_NAME_MAX} 字"
            )
        pkg.name = name
    if status is not None:
        if status not in (
            PackageStatus.DRAFT,
            PackageStatus.PUBLISHED,
            PackageStatus.ARCHIVED,
        ):
            raise MaterialPackageServiceError("INVALID_STATUS", "无效的材料包状态")
        pkg.status = status
    db.commit()
    db.refresh(pkg)
    return pkg


def delete_package(db: Session, pkg: MaterialPackage) -> None:
    """Delete a draft package. Snapshots make history — refuse if any exist."""
    if pkg.status != PackageStatus.DRAFT:
        raise MaterialPackageServiceError(
            "NOT_DRAFT", "只有草稿状态的材料包可以删除", 409
        )
    snapshot_count = int(
        db.scalar(
            select(func.count())
            .select_from(MaterialPackageSnapshot)
            .where(MaterialPackageSnapshot.package_id == pkg.id)
        )
        or 0
    )
    if snapshot_count > 0:
        raise MaterialPackageServiceError(
            "HAS_SNAPSHOTS", "该材料包已有历史快照，不能删除", 409
        )
    db.delete(pkg)
    db.commit()


def list_packages(
    db: Session, case_id: uuid.UUID, *, limit: int = 20, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    base = select(MaterialPackage).where(MaterialPackage.case_id == case_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.scalars(
        base.order_by(MaterialPackage.created_at.desc()).limit(limit).offset(offset)
    ).all()

    package_ids = [r.id for r in rows]
    item_counts: dict[uuid.UUID, int] = {}
    snapshot_counts: dict[uuid.UUID, int] = {}
    if package_ids:
        for pid, cnt in db.execute(
            select(MaterialPackageItem.package_id, func.count())
            .where(MaterialPackageItem.package_id.in_(package_ids))
            .group_by(MaterialPackageItem.package_id)
        ):
            item_counts[pid] = int(cnt)
        for pid, cnt in db.execute(
            select(MaterialPackageSnapshot.package_id, func.count())
            .where(MaterialPackageSnapshot.package_id.in_(package_ids))
            .group_by(MaterialPackageSnapshot.package_id)
        ):
            snapshot_counts[pid] = int(cnt)

    items = []
    for r in rows:
        items.append(
            {
                "package": r,
                "item_count": item_counts.get(r.id, 0),
                "snapshot_count": snapshot_counts.get(r.id, 0),
            }
        )
    return items, total


# ---------- items ----------


def _load_evidence_map(db: Session, case_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Evidence]:
    if not ids:
        return {}
    rows = db.scalars(
        select(Evidence).where(Evidence.id.in_(ids), Evidence.case_id == case_id)
    ).all()
    found = {r.id: r for r in rows}
    missing = ids - set(found)
    if missing:
        # Non-existent and cross-case ids produce the same error so the API
        # cannot be used to probe other users' evidence ids.
        raise MaterialPackageServiceError(
            "EVIDENCE_NOT_FOUND", "证据不存在或不属于当前案件"
        )
    return found


def save_items(
    db: Session,
    pkg: MaterialPackage,
    expected_draft_version: int,
    items: list[ItemInput],
) -> MaterialPackage:
    """Atomically replace the draft's items with the given order/content.

    Phase 9-C: publishing only records user confirmation — a PUBLISHED
    package stays editable. Only ARCHIVED locks items.
    """
    if pkg.status == PackageStatus.ARCHIVED:
        raise MaterialPackageServiceError(
            "NOT_EDITABLE", "已归档的材料包不能编辑条目", 409
        )
    if expected_draft_version != pkg.draft_version:
        raise MaterialPackageServiceError(
            "VERSION_CONFLICT",
            "材料包已被其他人修改，请重新加载后再次保存",
            409,
        )
    if len(items) > _MAX_ITEMS_PER_PACKAGE:
        raise MaterialPackageServiceError(
            "TOO_MANY_ITEMS", f"单个材料包最多 {_MAX_ITEMS_PER_PACKAGE} 条"
        )

    evidence_ids = [it.evidence_id for it in items]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise MaterialPackageServiceError(
            "DUPLICATE_EVIDENCE", "同一证据不能重复加入材料包"
        )
    for it in items:
        if it.display_name is not None and len(it.display_name.strip()) > _DISPLAY_NAME_MAX:
            raise MaterialPackageServiceError(
                "INVALID_ITEM", f"展示名称不能超过 {_DISPLAY_NAME_MAX} 字"
            )
        if it.proof_purpose is not None and len(it.proof_purpose) > _PROOF_PURPOSE_MAX:
            raise MaterialPackageServiceError(
                "INVALID_ITEM", f"拟证明事项不能超过 {_PROOF_PURPOSE_MAX} 字"
            )
        if it.review_status is not None and it.review_status not in (
            ItemReviewStatus.PENDING,
            ItemReviewStatus.APPROVED,
            ItemReviewStatus.REJECTED,
        ):
            raise MaterialPackageServiceError("INVALID_ITEM", "无效的审核状态")

    evidence_map = _load_evidence_map(db, pkg.case_id, set(evidence_ids))

    existing = {
        item.evidence_id: item
        for item in db.scalars(
            select(MaterialPackageItem).where(MaterialPackageItem.package_id == pkg.id)
        ).all()
    }

    keep_ids = set(evidence_ids)
    for evidence_id, item in existing.items():
        if evidence_id not in keep_ids:
            db.delete(item)
    db.flush()  # deletions land before the reorder insert/update pass

    for position, it in enumerate(items, start=1):
        evidence = evidence_map[it.evidence_id]
        item = existing.get(it.evidence_id)
        display_name = (it.display_name or "").strip() or evidence.title[:_DISPLAY_NAME_MAX]
        proof_purpose = (
            it.proof_purpose if it.proof_purpose is not None else evidence.proof_purpose
        )
        review_status = it.review_status or ItemReviewStatus.PENDING
        if item is None:
            item = MaterialPackageItem(
                package_id=pkg.id,
                evidence_id=it.evidence_id,
                item_order=position,
                display_number=position,
                display_name=display_name,
                proof_purpose=proof_purpose,
                review_status=review_status,
            )
            db.add(item)
        else:
            item.item_order = position
            item.display_number = position
            item.display_name = display_name
            item.proof_purpose = proof_purpose
            item.review_status = review_status

    pkg.draft_version += 1
    db.commit()
    db.refresh(pkg)
    return pkg


def package_detail(
    db: Session, pkg: MaterialPackage
) -> tuple[MaterialPackage, list[MaterialPackageItem], int]:
    """Package row + ordered items + snapshot count (one extra query)."""
    rows = db.scalars(
        select(MaterialPackageItem)
        .where(MaterialPackageItem.package_id == pkg.id)
        .order_by(MaterialPackageItem.item_order)
    ).all()
    snapshot_count = int(
        db.scalar(
            select(func.count())
            .select_from(MaterialPackageSnapshot)
            .where(MaterialPackageSnapshot.package_id == pkg.id)
        )
        or 0
    )
    return pkg, list(rows), snapshot_count


# ---------- snapshots ----------


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def create_snapshot(
    db: Session,
    pkg: MaterialPackage,
    user_id: uuid.UUID,
    expected_draft_version: int,
) -> MaterialPackageSnapshot:
    """Freeze the current draft into an immutable, self-contained snapshot."""
    if pkg.status == PackageStatus.ARCHIVED:
        raise MaterialPackageServiceError(
            "NOT_SNAPSHOTABLE", "已归档的材料包不能创建快照", 409
        )
    if expected_draft_version != pkg.draft_version:
        raise MaterialPackageServiceError(
            "VERSION_CONFLICT",
            "材料包已被其他人修改，请重新加载后再创建快照",
            409,
        )
    items = db.scalars(
        select(MaterialPackageItem)
        .where(MaterialPackageItem.package_id == pkg.id)
        .order_by(MaterialPackageItem.item_order)
    ).all()
    if not items:
        raise MaterialPackageServiceError(
            "EMPTY_PACKAGE", "材料包还没有条目，不能创建快照", 409
        )

    latest = db.scalar(
        select(MaterialPackageSnapshot)
        .where(MaterialPackageSnapshot.package_id == pkg.id)
        .order_by(MaterialPackageSnapshot.version.desc())
        .limit(1)
    )
    if latest is not None and latest.draft_version_captured == pkg.draft_version:
        # Nothing changed since the last snapshot: a double submit must not
        # create a byte-identical duplicate version.
        raise MaterialPackageServiceError(
            "SNAPSHOT_DUPLICATE", "自上一次快照后草稿没有变化，无需重复创建", 409
        )

    evidence_ids = [it.evidence_id for it in items]
    evidence_rows = db.scalars(
        select(Evidence).where(Evidence.id.in_(evidence_ids))
    ).all()
    evidence_map = {e.id: e for e in evidence_rows}

    captured_items: list[dict[str, Any]] = []
    for item in items:
        evidence = evidence_map.get(item.evidence_id)
        captured_items.append(
            {
                "item_id": str(item.id),
                "evidence_id": str(item.evidence_id),
                "evidence_number": evidence.evidence_number if evidence else None,
                "item_order": item.item_order,
                "display_number": item.display_number,
                "display_name": item.display_name,
                "proof_purpose": item.proof_purpose,
                "review_status": item.review_status,
                "evidence_title": evidence.title if evidence else None,
                "evidence_category": evidence.category if evidence else None,
                "source_file_id": str(evidence.source_file_id)
                if evidence and evidence.source_file_id
                else None,
                # Version marker used at read time to detect later changes.
                "evidence_updated_at": _iso(evidence.updated_at) if evidence else None,
            }
        )

    content = {
        "package": {"name": pkg.name, "status": pkg.status},
        "draft_version": pkg.draft_version,
        "captured_at": _iso(utcnow()),
        "items": captured_items,
    }
    next_version = int(latest.version) + 1 if latest else 1
    snapshot = MaterialPackageSnapshot(
        package_id=pkg.id,
        version=next_version,
        draft_version_captured=pkg.draft_version,
        content=content,
        created_by=user_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_snapshots(
    db: Session, pkg: MaterialPackage
) -> tuple[list[MaterialPackageSnapshot], int]:
    base = select(MaterialPackageSnapshot).where(
        MaterialPackageSnapshot.package_id == pkg.id
    )
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.scalars(base.order_by(MaterialPackageSnapshot.version.desc())).all()
    return list(rows), total


def get_snapshot(db: Session, pkg: MaterialPackage, version: int) -> MaterialPackageSnapshot:
    snap = db.scalar(
        select(MaterialPackageSnapshot).where(
            MaterialPackageSnapshot.package_id == pkg.id,
            MaterialPackageSnapshot.version == version,
        )
    )
    if snap is None:
        raise MaterialPackageServiceError(
            "SNAPSHOT_NOT_FOUND", "快照版本不存在.", 404
        )
    return snap


def snapshot_with_source_status(
    db: Session, snap: MaterialPackageSnapshot
) -> MaterialPackageSnapshot:
    """Annotate each stored item with the *current* source state.

    The stored content is never rewritten (rule 6/7); the extra
    `source_status` field is computed at read time so a deleted or edited
    source evidence is reported as an anomaly instead of being silently
    presented as still-valid history.
    """
    items = snap.content.get("items", []) if isinstance(snap.content, dict) else []
    ids = {uuid.UUID(it["evidence_id"]) for it in items if it.get("evidence_id")}
    current: dict[uuid.UUID, Evidence] = {}
    if ids:
        current = {e.id: e for e in db.scalars(select(Evidence).where(Evidence.id.in_(ids)))}

    annotated = []
    for it in items:
        entry = dict(it)
        eid = uuid.UUID(it["evidence_id"]) if it.get("evidence_id") else None
        evidence = current.get(eid) if eid else None
        if evidence is None:
            entry["source_status"] = "MISSING"
        else:
            captured_at = _parse_iso(it.get("evidence_updated_at"))
            if captured_at is not None and evidence.updated_at is not None:
                current_at = evidence.updated_at
                if current_at.tzinfo is None:
                    current_at = current_at.replace(tzinfo=timezone.utc)
                entry["source_status"] = (
                    "CHANGED" if current_at > captured_at else "OK"
                )
            else:
                entry["source_status"] = "OK"
        annotated.append(entry)

    payload = dict(snap.content) if isinstance(snap.content, dict) else {}
    payload["items"] = annotated
    snap.content = payload  # in-memory only; never committed
    return snap
