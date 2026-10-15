"""API route modules. `api_router` is mounted at `/api/v1` by `app.main`."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.routes import (
    analysis,
    auth,
    cases,
    claims,
    evidence,
    evidence_gaps,
    export,
    files,
    material_packages,
    review,
    timeline,
)

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(cases.router, tags=["cases"])
api_router.include_router(claims.router, tags=["claims"])
api_router.include_router(files.router, tags=["files"])
api_router.include_router(analysis.router, tags=["analysis"])
api_router.include_router(evidence.router, tags=["evidence"])
api_router.include_router(evidence_gaps.router, tags=["evidence-gaps"])
api_router.include_router(material_packages.router, tags=["material-packages"])
api_router.include_router(review.router, tags=["review"])
api_router.include_router(timeline.router, tags=["timeline"])
api_router.include_router(export.router, tags=["export"])

__all__ = [
    "analysis",
    "api_router",
    "auth",
    "cases",
    "claims",
    "evidence",
    "evidence_gaps",
    "export",
    "files",
    "material_packages",
    "review",
    "timeline",
]
