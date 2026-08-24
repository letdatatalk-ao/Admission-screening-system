"""
backend/app/api/v1/supervisors.py

Faculty supervisor profiles and applicant-to-supervisor matching.

Endpoints:
  GET    /supervisors              — list all supervisors
  POST   /supervisors              — create a supervisor
  PATCH  /supervisors/{id}         — update a supervisor
  DELETE /supervisors/{id}         — delete a supervisor
  GET    /supervisors/{id}/matches — applicants matched to this supervisor
  GET    /supervisors/applicant/{applicant_id}/matches — supervisors matched to an applicant
"""

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.db.database import get_db
from backend.app.db.models import ApplicantSupervisorMatch, SupervisorProfile, Applicant
from backend.app.db.repositories.supervisor_repo import (
    get_all_supervisors,
    get_supervisor,
    create_supervisor,
    update_supervisor,
    delete_supervisor,
    get_matches_for_applicant,
    get_matches_for_supervisor,
)
from backend.app.api.v1.auth import check_evaluator, check_admin

router = APIRouter(prefix="/supervisors", tags=["supervisors"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SupervisorCreate(BaseModel):
    faculty_name: str = Field(..., min_length=2, max_length=300)
    email: Optional[str] = None
    department: Optional[str] = None
    research_areas: List[str] = Field(default_factory=list)
    max_phd_students: int = Field(default=2, ge=0)
    current_phd_count: int = Field(default=0, ge=0)
    is_accepting_students: bool = True


class SupervisorUpdate(BaseModel):
    faculty_name: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    research_areas: Optional[List[str]] = None
    max_phd_students: Optional[int] = Field(default=None, ge=0)
    current_phd_count: Optional[int] = Field(default=None, ge=0)
    is_accepting_students: Optional[bool] = None


class SupervisorOut(BaseModel):
    id: uuid.UUID
    faculty_name: str
    email: Optional[str]
    department: Optional[str]
    research_areas: Optional[List[str]]
    max_phd_students: int
    current_phd_count: int
    is_accepting_students: bool

    model_config = {"from_attributes": True}


class MatchOut(BaseModel):
    supervisor_id: uuid.UUID
    faculty_name: str
    department: Optional[str]
    match_score: float
    matched_keywords: Optional[List[str]]

    model_config = {"from_attributes": True}


class ApplicantMatchOut(BaseModel):
    applicant_id: uuid.UUID
    full_name: Optional[str]
    match_score: float
    matched_keywords: Optional[List[str]]

    model_config = {"from_attributes": True}


# ── CRUD endpoints ────────────────────────────────────────────────────────────

@router.get("/", response_model=List[SupervisorOut])
async def list_supervisors(
    accepting_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    return await get_all_supervisors(db, accepting_only=accepting_only)


@router.post("/", response_model=SupervisorOut, status_code=status.HTTP_201_CREATED)
async def create_supervisor_endpoint(
    body: SupervisorCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_admin),
):
    sup = await create_supervisor(db, **body.model_dump())
    await db.commit()
    await db.refresh(sup)
    return sup


@router.patch("/{supervisor_id}", response_model=SupervisorOut)
async def update_supervisor_endpoint(
    supervisor_id: uuid.UUID,
    body: SupervisorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_admin),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    sup = await update_supervisor(db, supervisor_id, updates)
    if sup is None:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    await db.commit()
    await db.refresh(sup)
    return sup


@router.delete("/{supervisor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supervisor_endpoint(
    supervisor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_admin),
):
    deleted = await delete_supervisor(db, supervisor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    await db.commit()


# ── Match query endpoints ─────────────────────────────────────────────────────

@router.get("/{supervisor_id}/matches", response_model=List[ApplicantMatchOut])
async def get_supervisor_matches(
    supervisor_id: uuid.UUID,
    min_score: float = 0.0,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    """List applicants matched to this supervisor, ordered by match score."""
    sup = await get_supervisor(db, supervisor_id)
    if sup is None:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    raw_matches = await get_matches_for_supervisor(db, supervisor_id)

    result = []
    for m in raw_matches:
        if m.match_score < min_score:
            continue
        app_result = await db.execute(
            select(Applicant).where(Applicant.id == m.applicant_id)
        )
        app = app_result.scalar_one_or_none()
        result.append(ApplicantMatchOut(
            applicant_id=m.applicant_id,
            full_name=app.full_name if app else None,
            match_score=float(m.match_score),
            matched_keywords=m.matched_keywords,
        ))
    return result


@router.get("/applicant/{applicant_id}/matches", response_model=List[MatchOut])
async def get_applicant_supervisor_matches(
    applicant_id: uuid.UUID,
    min_score: float = 0.0,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    """List supervisors matched to this applicant, ordered by match score."""
    raw_matches = await get_matches_for_applicant(db, applicant_id)

    result = []
    for m in raw_matches:
        if m.match_score < min_score:
            continue
        sup = await get_supervisor(db, m.supervisor_id)
        if sup is None:
            continue
        result.append(MatchOut(
            supervisor_id=m.supervisor_id,
            faculty_name=sup.faculty_name,
            department=sup.department,
            match_score=float(m.match_score),
            matched_keywords=m.matched_keywords,
        ))
    return result
