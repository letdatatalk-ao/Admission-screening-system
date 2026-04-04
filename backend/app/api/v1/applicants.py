import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, ExtractedMetrics, Publication
from backend.app.db.repositories.applicant_repo import (
    get_applicant, get_extracted_metrics, list_applicants
)
from backend.app.db.repositories.publication_repo import list_publications
from backend.app.api.v1.schemas import ApplicantRead, ApplicantDetail

router = APIRouter(tags=["Applicants"])

@router.get("/applicants", response_model=List[ApplicantRead])
async def get_applicants_list(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # Sous-requête pour compter les publications par candidat
    pub_sub = (
        select(Publication.applicant_id, func.count(Publication.id).label("cnt"))
        .group_by(Publication.applicant_id)
    ).subquery()

    # Requête principale avec double jointure (Metrics + PubCount)
    query = (
        select(
            Applicant.id, Applicant.application_ref, Applicant.full_name,
            Applicant.email, Applicant.nationality, Applicant.status,
            Applicant.needs_human_review, Applicant.pairing_complete,
            Applicant.last_composite_score, Applicant.last_rank,
            ExtractedMetrics.bsc_uni_name, ExtractedMetrics.bsc_qs_rank,
            ExtractedMetrics.bsc_gpa_normalised,
            ExtractedMetrics.msc_uni_name, ExtractedMetrics.msc_qs_rank,
            ExtractedMetrics.msc_gpa_normalised, ExtractedMetrics.msc_absent,
            ExtractedMetrics.global_confidence,
            func.coalesce(pub_sub.c.cnt, 0).label("pub_count")
        )
        .outerjoin(ExtractedMetrics, Applicant.id == ExtractedMetrics.applicant_id)
        .outerjoin(pub_sub, Applicant.id == pub_sub.c.applicant_id)
        .where(Applicant.session_id == session_id)
        .order_by(Applicant.last_rank.asc().nulls_last())
    )
    
    result = await db.execute(query)
    return result.mappings().all()

@router.get("/applicants/{applicant_id}", response_model=ApplicantDetail)
async def get_applicant_details(applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    applicant = await get_applicant(db, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    applicant.metrics = await get_extracted_metrics(db, applicant_id)
    applicant.publications = await list_publications(db, applicant_id)
    return applicant

@router.patch("/applicants/{applicant_id}/metrics")
async def update_metrics(applicant_id: uuid.UUID, updated_data: dict = Body(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExtractedMetrics).where(ExtractedMetrics.applicant_id == applicant_id))
    db_metrics = result.scalar_one_or_none()
    if not db_metrics:
        db_metrics = ExtractedMetrics(applicant_id=applicant_id)
        db.add(db_metrics)
    for key, value in updated_data.items():
        if hasattr(db_metrics, key):
            setattr(db_metrics, key, value)
    await db.commit()
    return {"status": "success"}