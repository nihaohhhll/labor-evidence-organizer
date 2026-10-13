"""Analysis routes: trigger parsing for a file or a whole case."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.deps import CurrentUser, DbDep, owned_case_or_404, owned_file_or_404
from app.schemas import AnalysisOut, AnalysisTriggerOut
from app.services import analysis as analysis_service
from app.services import files as file_service

router = APIRouter()


def _analysis_out(row) -> AnalysisOut:
    out = AnalysisOut.model_validate(row)
    structured = row.structured_json or {}
    out.dates = list(structured.get("dates") or [])
    out.amounts = list(structured.get("amounts") or [])
    out.persons = list(structured.get("persons") or [])
    out.organizations = list(structured.get("organizations") or [])
    out.events = list(structured.get("events") or [])
    out.summary = structured.get("summary")
    out.proof_purpose = structured.get("proof_purpose")
    return out


@router.post("/files/{file_id}/analyze", response_model=AnalysisOut)
def analyze_one(file_id: uuid.UUID, db: DbDep, user: CurrentUser) -> AnalysisOut:
    """Parse and analyze a single file, then emit an evidence suggestion.

    Deliberately a plain `def`: FastAPI runs these in a worker thread, where
    the service layer may safely call `asyncio.run()` for the async provider
    protocols. Declaring it `async def` would put the call on the event loop
    and raise "asyncio.run() cannot be called from a running event loop".
    """
    file = owned_file_or_404(db, file_id, user.id)

    try:
        analysis = analysis_service.analyze_file(db, file)
    except analysis_service.AnalysisError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message})
    except file_service.FileServiceError as exc:
        # e.g. INVALID_TRANSITION: a FAILED file must be retried before it
        # can re-enter processing — surface as a state conflict, not a 500.
        raise HTTPException(409, detail={"code": exc.code, "message": exc.message})

    analysis_service.suggest_evidence_from_analysis(db, file.case_id, analysis, file=file)
    db.commit()
    return _analysis_out(analysis)


@router.get("/files/{file_id}/analysis", response_model=AnalysisOut)
def get_analysis(file_id: uuid.UUID, db: DbDep, user: CurrentUser) -> AnalysisOut:
    """Return the most recent successful analysis for a file."""
    file = owned_file_or_404(db, file_id, user.id)

    row = analysis_service.latest_analysis(db, file.id)
    if row is None:
        raise HTTPException(
            404, detail={"code": "ANALYSIS_NOT_FOUND", "message": "该文件还没有解析结果。"}
        )
    return _analysis_out(row)


@router.post("/cases/{case_id}/analyze", response_model=AnalysisTriggerOut)
def analyze_case(
    case_id: uuid.UUID, db: DbDep, user: CurrentUser
) -> AnalysisTriggerOut:
    """Analyze every pending file in a case (batch path)."""
    case = owned_case_or_404(db, case_id, user.id)

    analyses = analysis_service.analyze_case_files(db, case.id)
    return AnalysisTriggerOut(
        analyzed=len(analyses),
        failed=len(file_service.list_files(db, case.id))
        - sum(1 for f in file_service.list_files(db, case.id) if f.status == "COMPLETED"),
    )
