"""Material package routes (Phase 9-A).

The selectable-evidence list for the editor is the existing
`GET /cases/{case_id}/evidence` endpoint — nothing is duplicated here.
Service errors are translated to the project-wide error envelope; ownership
misses become 404 so ids cannot be probed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.deps import CurrentUser, DbDep
from app.models.material_package import MaterialPackage, MaterialPackageItem
from app.routes.cases import _get_owned
from app.schemas import (
    ExportJobOut,
    ExportListOut,
    MaterialPackageCreate,
    MaterialPackageDetailOut,
    MaterialPackageExportIn,
    MaterialPackageItemOut,
    MaterialPackageItemsSaveIn,
    MaterialPackageListOut,
    MaterialPackageOut,
    MaterialPackageSnapshotCreateIn,
    MaterialPackageSnapshotListOut,
    MaterialPackageSnapshotOut,
    MaterialPackageUpdate,
)
from app.services import export as export_service
from app.services import material_packages as pkg_service
from app.services.audit import AuditAction, record as audit
from app.services.export import ExportError
from app.services.material_packages import (
    ItemInput,
    MaterialPackageServiceError,
)

router = APIRouter()


def _translate(exc: MaterialPackageServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": exc.message},
    )


def _owned_package(db, user, package_id: uuid.UUID) -> MaterialPackage:
    try:
        return pkg_service.get_owned_package(db, package_id, user.id)
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None


def _item_out(item: MaterialPackageItem) -> MaterialPackageItemOut:
    evidence = item.evidence
    return MaterialPackageItemOut(
        id=item.id,
        evidence_id=item.evidence_id,
        evidence_number=evidence.evidence_number if evidence else None,
        source_file_id=evidence.source_file_id if evidence else None,
        item_order=item.item_order,
        display_number=item.display_number,
        display_name=item.display_name,
        proof_purpose=item.proof_purpose,
        review_status=item.review_status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _detail_out(db, pkg: MaterialPackage) -> MaterialPackageDetailOut:
    # Built field-by-field: `items` on the ORM object are raw model rows and
    # need the evidence projection in `_item_out`, so model_validate would
    # both mis-serialise them and miss the counts.
    pkg, items, snapshot_count = pkg_service.package_detail(db, pkg)
    return MaterialPackageDetailOut(
        id=pkg.id,
        case_id=pkg.case_id,
        name=pkg.name,
        status=pkg.status,
        draft_version=pkg.draft_version,
        item_count=len(items),
        snapshot_count=snapshot_count,
        created_at=pkg.created_at,
        updated_at=pkg.updated_at,
        items=[_item_out(i) for i in items],
    )


def _summary_out(pkg: MaterialPackage, item_count: int, snapshot_count: int) -> MaterialPackageOut:
    out = MaterialPackageOut.model_validate(pkg)
    out.item_count = item_count
    out.snapshot_count = snapshot_count
    return out


# ---------- package CRUD ----------


@router.post(
    "/cases/{case_id}/material-packages",
    response_model=MaterialPackageDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_material_package(
    case_id: uuid.UUID, body: MaterialPackageCreate, db: DbDep, user: CurrentUser
) -> MaterialPackageDetailOut:
    _get_owned(db, user, case_id)
    try:
        pkg = pkg_service.create_package(db, case_id, user.id, body.name)
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None
    audit(
        db,
        action=AuditAction.MATERIAL_PACKAGE_CREATED,
        user_id=user.id,
        case_id=case_id,
        entity_type="material_package",
        entity_id=pkg.id,
        metadata={"name": pkg.name},
    )
    return _detail_out(db, pkg)


@router.get("/cases/{case_id}/material-packages", response_model=MaterialPackageListOut)
def list_material_packages(
    case_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    limit: int = 20,
    offset: int = 0,
) -> MaterialPackageListOut:
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    _get_owned(db, user, case_id)
    rows, total = pkg_service.list_packages(db, case_id, limit=limit, offset=offset)
    return MaterialPackageListOut(
        items=[_summary_out(r["package"], r["item_count"], r["snapshot_count"]) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/material-packages/{package_id}", response_model=MaterialPackageDetailOut)
def get_material_package(
    package_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> MaterialPackageDetailOut:
    return _detail_out(db, _owned_package(db, user, package_id))


@router.patch("/material-packages/{package_id}", response_model=MaterialPackageDetailOut)
def update_material_package(
    package_id: uuid.UUID, body: MaterialPackageUpdate, db: DbDep, user: CurrentUser
) -> MaterialPackageDetailOut:
    pkg = _owned_package(db, user, package_id)
    payload = body.model_dump(exclude_unset=True)
    try:
        pkg = pkg_service.update_package(
            db, pkg, name=payload.get("name"), status=payload.get("status")
        )
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None
    audit(
        db,
        action=AuditAction.MATERIAL_PACKAGE_UPDATED,
        user_id=user.id,
        case_id=pkg.case_id,
        entity_type="material_package",
        entity_id=pkg.id,
        metadata={"changed_fields": sorted(payload)},
    )
    return _detail_out(db, pkg)


@router.delete("/material-packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material_package(
    package_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> Response:
    pkg = _owned_package(db, user, package_id)
    try:
        pkg_service.delete_package(db, pkg)
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None
    audit(
        db,
        action=AuditAction.MATERIAL_PACKAGE_DELETED,
        user_id=user.id,
        case_id=pkg.case_id,
        entity_type="material_package",
        entity_id=package_id,
        metadata={"name": pkg.name},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- items ----------


@router.get("/material-packages/{package_id}/items", response_model=list[MaterialPackageItemOut])
def list_material_package_items(
    package_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> list[MaterialPackageItemOut]:
    pkg = _owned_package(db, user, package_id)
    _, items, _ = pkg_service.package_detail(db, pkg)
    return [_item_out(i) for i in items]


@router.put("/material-packages/{package_id}/items", response_model=MaterialPackageDetailOut)
def save_material_package_items(
    package_id: uuid.UUID, body: MaterialPackageItemsSaveIn, db: DbDep, user: CurrentUser
) -> MaterialPackageDetailOut:
    pkg = _owned_package(db, user, package_id)
    inputs = [
        ItemInput(
            evidence_id=it.evidence_id,
            display_name=it.display_name,
            proof_purpose=it.proof_purpose,
            review_status=it.review_status,
        )
        for it in body.items
    ]
    try:
        pkg = pkg_service.save_items(db, pkg, body.expected_draft_version, inputs)
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None
    audit(
        db,
        action=AuditAction.MATERIAL_PACKAGE_ITEMS_SAVED,
        user_id=user.id,
        case_id=pkg.case_id,
        entity_type="material_package",
        entity_id=pkg.id,
        metadata={"item_count": len(inputs), "draft_version": pkg.draft_version},
    )
    return _detail_out(db, pkg)


# ---------- snapshots ----------


@router.post(
    "/material-packages/{package_id}/snapshots",
    response_model=MaterialPackageSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
def create_material_package_snapshot(
    package_id: uuid.UUID,
    body: MaterialPackageSnapshotCreateIn,
    db: DbDep,
    user: CurrentUser,
) -> MaterialPackageSnapshotOut:
    pkg = _owned_package(db, user, package_id)
    try:
        snap = pkg_service.create_snapshot(db, pkg, user.id, body.expected_draft_version)
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None
    audit(
        db,
        action=AuditAction.MATERIAL_PACKAGE_SNAPSHOT_CREATED,
        user_id=user.id,
        case_id=pkg.case_id,
        entity_type="material_package_snapshot",
        entity_id=snap.id,
        metadata={"package_id": str(pkg.id), "version": snap.version},
    )
    return MaterialPackageSnapshotOut(
        id=snap.id,
        package_id=snap.package_id,
        version=snap.version,
        draft_version_captured=snap.draft_version_captured,
        created_at=snap.created_at,
        content=snap.content,
    )


@router.get(
    "/material-packages/{package_id}/snapshots",
    response_model=MaterialPackageSnapshotListOut,
)
def list_material_package_snapshots(
    package_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> MaterialPackageSnapshotListOut:
    pkg = _owned_package(db, user, package_id)
    rows, total = pkg_service.list_snapshots(db, pkg)
    return MaterialPackageSnapshotListOut(
        snapshots=[
            MaterialPackageSnapshotOut(
                id=s.id,
                package_id=s.package_id,
                version=s.version,
                draft_version_captured=s.draft_version_captured,
                created_at=s.created_at,
                content=s.content,
            )
            for s in rows
        ],
        total=total,
    )


@router.get(
    "/material-packages/{package_id}/snapshots/{version}",
    response_model=MaterialPackageSnapshotOut,
)
def get_material_package_snapshot(
    package_id: uuid.UUID, version: int, db: DbDep, user: CurrentUser
) -> MaterialPackageSnapshotOut:
    pkg = _owned_package(db, user, package_id)
    try:
        snap = pkg_service.get_snapshot(db, pkg, version)
    except MaterialPackageServiceError as exc:
        raise _translate(exc) from None
    snap = pkg_service.snapshot_with_source_status(db, snap)
    return MaterialPackageSnapshotOut(
        id=snap.id,
        package_id=snap.package_id,
        version=snap.version,
        draft_version_captured=snap.draft_version_captured,
        created_at=snap.created_at,
        content=snap.content,
    )


# ---------- exports (Phase 9-C: 成卷输出) ----------


def _resolve_snapshot(db, pkg: MaterialPackage, version: int | None):
    """Latest snapshot when unspecified; SNAPSHOT_REQUIRED when none exist."""
    if version is not None:
        try:
            return pkg_service.get_snapshot(db, pkg, version)
        except MaterialPackageServiceError as exc:
            raise _translate(exc) from None
    rows, _ = pkg_service.list_snapshots(db, pkg)
    if not rows:
        raise _translate(
            MaterialPackageServiceError(
                "SNAPSHOT_REQUIRED",
                "尚无快照：请先保存草稿并创建快照后再导出",
                409,
            )
        )
    return rows[0]


@router.post(
    "/material-packages/{package_id}/exports",
    response_model=ExportJobOut,
    status_code=status.HTTP_201_CREATED,
)
def create_material_package_export(
    package_id: uuid.UUID,
    body: MaterialPackageExportIn,
    db: DbDep,
    user: CurrentUser,
) -> ExportJobOut:
    pkg = _owned_package(db, user, package_id)
    fmt = body.format.lower()
    snapshot = _resolve_snapshot(db, pkg, body.snapshot_version)
    gap_result = None
    if body.include_gap_appendix:
        gap_result = export_service.latest_gap_result(db, pkg.case_id)
        if gap_result is None:
            raise _translate(
                MaterialPackageServiceError(
                    "GAP_APPENDIX_UNAVAILABLE",
                    "尚无可用的材料缺口分析结果，无法生成附录",
                    409,
                )
            )
    try:
        job = export_service.build_package_export(
            db,
            pkg.case,
            pkg,
            snapshot,
            fmt,
            include_gap_appendix=body.include_gap_appendix,
            gap_result=gap_result,
        )
    except ExportError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from None
    audit(
        db,
        action=AuditAction.EXPORT_CREATED,
        user_id=user.id,
        case_id=pkg.case_id,
        entity_type="export",
        entity_id=job.id,
        metadata={
            "format": job.format,
            "status": job.status,
            "package_id": str(pkg.id),
            "snapshot_version": job.snapshot_version,
            "include_gap_appendix": job.include_gap_appendix,
        },
    )
    return ExportJobOut.model_validate(job)


@router.get(
    "/material-packages/{package_id}/exports",
    response_model=ExportListOut,
)
def list_material_package_exports(
    package_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    limit: int = 100,
    offset: int = 0,
) -> ExportListOut:
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    pkg = _owned_package(db, user, package_id)
    rows, total = export_service.list_package_exports(
        db, pkg.id, limit=limit, offset=offset
    )
    return ExportListOut(
        exports=[ExportJobOut.model_validate(r) for r in rows], total=total
    )
