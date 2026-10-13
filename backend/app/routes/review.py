"""Human review routes: list pending items, apply user values, confirm.

The invariant this module exists to protect:

    AI value = A, user value = B  =>  the system must show B.

A later re-analysis writes a *new* analysis row; it never edits the entity a
user has already touched (docs/14_AI_CODING_AGENT_RULES).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.deps import CurrentUser, DbDep, owned_case_or_404
from app.services.audit import AuditAction, record as audit
from app.models.evidence import Evidence
from app.models.event import Event
from app.models.review import ReviewItem
from app.schemas import ReviewItemOut, ReviewListOut, ReviewResolveIn, ReviewResolvedOut
from app.services import files as file_service

router = APIRouter()

_ENTITY_MODELS = {"evidence": Evidence, "event": Event}


def _get_owned_review_item(db, user, item_id: uuid.UUID) -> ReviewItem:
    item = db.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(404, detail={"code": "REVIEW_ITEM_NOT_FOUND", "message": "Review item not found."})
    owned_case_or_404(db, item.case_id, user.id)
    return item


@router.get("/cases/{case_id}/review-items", response_model=ReviewListOut)
def list_review_items(
    case_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    status: str | None = Query(default="PENDING"),
) -> ReviewListOut:
    case = owned_case_or_404(db, case_id, user.id)

    stmt = select(ReviewItem).where(ReviewItem.case_id == case.id)
    if status:
        stmt = stmt.where(ReviewItem.status == status)
    rows = list(db.scalars(stmt.order_by(ReviewItem.created_at.asc())).all())
    return ReviewListOut(items=[ReviewItemOut.model_validate(r) for r in rows], total=len(rows))


@router.patch("/review-items/{item_id}", response_model=ReviewItemOut)
def save_user_value(
    item_id: uuid.UUID, body: ReviewResolveIn, db: DbDep, user: CurrentUser
) -> ReviewItemOut:
    """Store the user's own value without confirming yet."""
    item = _get_owned_review_item(db, user, item_id)
    item.user_value = body.user_value
    db.commit()
    db.refresh(item)
    return ReviewItemOut.model_validate(item)


@router.post("/review-items/{item_id}/confirm", response_model=ReviewResolvedOut)
def confirm_review_item(
    item_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ReviewResolvedOut:
    """Apply the review decision to the underlying entity.

    The user's value wins over the AI's. If the field was edited, the entity
    records it so future analyses must not overwrite it.
    """
    item = _get_owned_review_item(db, user, item_id)

    model = _ENTITY_MODELS.get(item.entity_type)
    if model is None:
        raise HTTPException(400, detail={"code": "UNKNOWN_ENTITY", "message": "未知的实体类型。"})

    entity = db.get(model, item.entity_id)
    chosen = item.user_value if item.user_value is not None else item.ai_value
    applied: dict[str, object] = {}

    if entity is not None and isinstance(chosen, dict):
        for key, value in chosen.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
                applied[key] = value
                # Protect the human's choice from later AI passes.
                if item.entity_type == "evidence" and hasattr(entity, "mark_edited"):
                    entity.mark_edited(key)

    item.status = "CONFIRMED"
    item.user_value = chosen
    db.commit()

    audit(
        db,
        action=AuditAction.REVIEW_CONFIRMED,
        user_id=user.id,
        case_id=item.case_id,
        entity_type="review_item",
        entity_id=item.id,
        # Field names only; values may contain bank or ID details.
        metadata={"field_name": item.field_name, "used_user_value": item.user_value is not None},
    )
    return ReviewResolvedOut(id=item.id, status=item.status, applied=applied)


@router.post("/review-items/{item_id}/discard", response_model=ReviewResolvedOut)
def discard_review_item(
    item_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> ReviewResolvedOut:
    """Keep the AI's suggestion out of the final evidence set."""
    item = _get_owned_review_item(db, user, item_id)
    item.status = "DISCARDED"
    db.commit()
    audit(
        db,
        action=AuditAction.REVIEW_DISCARDED,
        user_id=user.id,
        case_id=item.case_id,
        entity_type="review_item",
        entity_id=item.id,
        metadata={"field_name": item.field_name},
    )
    return ReviewResolvedOut(id=item.id, status=item.status, applied={})
