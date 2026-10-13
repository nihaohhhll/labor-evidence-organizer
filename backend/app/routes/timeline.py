"""Timeline routes: build, list, edit, merge and delete events."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, DbDep, owned_case_or_404
from app.models.event import Event
from app.schemas import (
    EventCreate,
    EventDetailOut,
    EventListOut,
    EventMergeIn,
    EventUpdate,
)
from app.services import files as file_service
from app.services.timeline import build_timeline, merge_events

router = APIRouter()


def _get_owned_event(db, user, event_id: uuid.UUID) -> Event:
    row = db.get(Event, event_id)
    if row is None:
        raise HTTPException(404, detail={"code": "EVENT_NOT_FOUND", "message": "Event not found."})
    owned_case_or_404(db, row.case_id, user.id)
    return row


@router.get("/cases/{case_id}/events", response_model=EventListOut)
def list_events(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> EventListOut:
    case = owned_case_or_404(db, case_id, user.id)

    rows = list(
        db.scalars(
            select(Event)
            .where(Event.case_id == case.id, Event.merged_into_id.is_(None))
            .order_by(Event.event_date.asc().nulls_last(), Event.event_time.asc().nulls_last())
        ).all()
    )
    return EventListOut(events=[EventDetailOut.model_validate(r) for r in rows], total=len(rows))


@router.post("/cases/{case_id}/events/build", response_model=EventListOut)
def build_case_timeline(case_id: uuid.UUID, db: DbDep, user: CurrentUser) -> EventListOut:
    """Derive timeline events from confirmed evidence (US-005)."""
    case = owned_case_or_404(db, case_id, user.id)

    build_timeline(db, case.id)
    db.commit()
    return list_events(case.id, db, user)


@router.post("/cases/{case_id}/events", response_model=EventDetailOut, status_code=201)
def create_event(
    case_id: uuid.UUID, body: EventCreate, db: DbDep, user: CurrentUser
) -> EventDetailOut:
    case = owned_case_or_404(db, case_id, user.id)

    row = Event(
        case_id=case.id,
        event_date=body.event_date,
        event_time=body.event_time,
        precision=body.precision,
        title=body.title,
        description=body.description,
        confidence=None,
        review_status="CONFIRMED",  # human-created, so already confirmed
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return EventDetailOut.model_validate(row)


@router.get("/events/{event_id}", response_model=EventDetailOut)
def get_event(event_id: uuid.UUID, db: DbDep, user: CurrentUser) -> EventDetailOut:
    return EventDetailOut.model_validate(_get_owned_event(db, user, event_id))


@router.patch("/events/{event_id}", response_model=EventDetailOut)
def update_event(
    event_id: uuid.UUID, body: EventUpdate, db: DbDep, user: CurrentUser
) -> EventDetailOut:
    row = _get_owned_event(db, user, event_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return EventDetailOut.model_validate(row)


@router.post("/events/merge", response_model=EventDetailOut)
def merge(
    body: EventMergeIn, db: DbDep, user: CurrentUser
) -> EventDetailOut:
    """Collapse several events into one survivor (US: 合并)."""
    try:
        survivor = merge_events(db, user.id, body.event_ids, body.title)
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "MERGE_FAILED", "message": str(exc)})
    return EventDetailOut.model_validate(survivor)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: uuid.UUID, db: DbDep, user: CurrentUser) -> Response:
    row = _get_owned_event(db, user, event_id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
