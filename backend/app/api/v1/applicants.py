import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, ExtractedMetrics, Publication, Venue
from backend.app.db.repositories.applicant_repo import (
    get_applicant, get_extracted_metrics, list_applicants
)
from backend.app.db.repositories.publication_repo import list_publications, get_publication, update_publication, delete_publication
from backend.app.api.v1.schemas import ApplicantRead, ApplicantDetail

router = APIRouter(tags=["Applicants"])


@router.get("/applicants", response_model=List[ApplicantRead])
async def get_applicants_list(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    # Sous-requête : nombre de publications par candidat
    pub_sub = (
        select(
            Publication.applicant_id,
            func.count(Publication.id).label("cnt")
        )
        .group_by(Publication.applicant_id)
        .subquery()
    )

    query = (
        select(
            Applicant.id,
            Applicant.application_ref,
            Applicant.full_name,
            Applicant.email,
            Applicant.nationality,
            Applicant.status,
            Applicant.needs_human_review,
            Applicant.pairing_complete,
            Applicant.last_composite_score,
            Applicant.last_rank,
            Applicant.created_at,
            ExtractedMetrics.bsc_uni_name,
            ExtractedMetrics.bsc_qs_rank,
            ExtractedMetrics.bsc_gpa_raw,
            ExtractedMetrics.bsc_gpa_scale,
            ExtractedMetrics.bsc_gpa_normalised,
            ExtractedMetrics.msc_uni_name,
            ExtractedMetrics.msc_qs_rank,
            ExtractedMetrics.msc_gpa_raw,
            ExtractedMetrics.msc_gpa_scale,
            ExtractedMetrics.msc_gpa_normalised,
            ExtractedMetrics.msc_absent,
            ExtractedMetrics.global_confidence,
            ExtractedMetrics.llm_used,
            ExtractedMetrics.model_used,
            func.coalesce(pub_sub.c.cnt, 0).label("pub_count")
        )
        .outerjoin(ExtractedMetrics, Applicant.id == ExtractedMetrics.applicant_id)
        .outerjoin(pub_sub, Applicant.id == pub_sub.c.applicant_id)
        .where(Applicant.session_id == session_id)
        .order_by(Applicant.last_rank.asc().nulls_last())
    )

    result = await db.execute(query)
    rows = result.mappings().all()
    
    # Convertir les résultats en dictionnaires compatibles avec le schéma
    applicants = []
    for row in rows:
        applicant_dict = {
            "id": row["id"],
            "application_ref": row["application_ref"],
            "full_name": row["full_name"],
            "email": row["email"],
            "nationality": row["nationality"],
            "status": row["status"],
            "needs_human_review": row["needs_human_review"],
            "pairing_complete": row["pairing_complete"],
            "last_composite_score": row["last_composite_score"],
            "last_rank": row["last_rank"],
            "bsc_uni_name": row["bsc_uni_name"],
            "bsc_qs_rank": row["bsc_qs_rank"],
            "bsc_gpa_raw": row["bsc_gpa_raw"],
            "bsc_gpa_scale": row["bsc_gpa_scale"],
            "bsc_gpa_normalised": row["bsc_gpa_normalised"],
            "msc_uni_name": row["msc_uni_name"],
            "msc_qs_rank": row["msc_qs_rank"],
            "msc_gpa_raw": row["msc_gpa_raw"],
            "msc_gpa_scale": row["msc_gpa_scale"],
            "msc_gpa_normalised": row["msc_gpa_normalised"],
            "msc_absent": row["msc_absent"] if row["msc_absent"] is not None else False,
            "global_confidence": row["global_confidence"] if row["global_confidence"] is not None else 0.0,
            "llm_used": row["llm_used"] if row["llm_used"] is not None else False,
            "model_used": row["model_used"],
            "pub_count": row["pub_count"]
        }
        applicants.append(ApplicantRead(**applicant_dict))
    
    return applicants


@router.get("/applicants/{applicant_id}", response_model=ApplicantDetail)
async def get_applicant_details(
    applicant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    applicant = await get_applicant(db, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    
    metrics = await get_extracted_metrics(db, applicant_id)
    publications = await list_publications(db, applicant_id)
    
    # Convertir les publications
    pubs_with_venue = []
    for pub in publications:
        pub_dict = {
            "id": str(pub.id),
            "title": pub.title,
            "year": pub.year,
            "pub_type": pub.pub_type,
            "authors_raw": pub.authors_raw,
            "author_position": pub.author_position,
            "total_authors": pub.total_authors,
            "first_author": pub.first_author if pub.first_author else False,
            "contribution_score": float(pub.contribution_score) if pub.contribution_score else 0.0,
            "venue_name": pub.venue.name if pub.venue else None
        }
        pubs_with_venue.append(pub_dict)
    
    # Construire la réponse
    response_data = {
        "id": str(applicant.id),
        "application_ref": applicant.application_ref,
        "full_name": applicant.full_name,
        "email": applicant.email,
        "nationality": applicant.nationality,
        "status": applicant.status,
        "needs_human_review": applicant.needs_human_review,
        "pairing_complete": applicant.pairing_complete,
        "last_composite_score": applicant.last_composite_score,
        "last_rank": applicant.last_rank,
        "cv_document_id": str(applicant.cv_document_id) if applicant.cv_document_id else None,
        "transcript_document_id": str(applicant.transcript_document_id) if applicant.transcript_document_id else None,
        "created_at": applicant.created_at,
        "publications": pubs_with_venue
    }
    
    # Ajouter les métriques si elles existent
    if metrics:
        response_data["bsc_uni_name"] = metrics.bsc_uni_name
        response_data["bsc_qs_rank"] = metrics.bsc_qs_rank
        response_data["bsc_gpa_raw"] = float(metrics.bsc_gpa_raw) if metrics.bsc_gpa_raw else None
        response_data["bsc_gpa_scale"] = float(metrics.bsc_gpa_scale) if metrics.bsc_gpa_scale else None
        response_data["bsc_gpa_normalised"] = float(metrics.bsc_gpa_normalised) if metrics.bsc_gpa_normalised else None
        response_data["msc_uni_name"] = metrics.msc_uni_name
        response_data["msc_qs_rank"] = metrics.msc_qs_rank
        response_data["msc_gpa_raw"] = float(metrics.msc_gpa_raw) if metrics.msc_gpa_raw else None
        response_data["msc_gpa_scale"] = float(metrics.msc_gpa_scale) if metrics.msc_gpa_scale else None
        response_data["msc_gpa_normalised"] = float(metrics.msc_gpa_normalised) if metrics.msc_gpa_normalised else None
        response_data["msc_absent"] = metrics.msc_absent if metrics.msc_absent else False
        response_data["global_confidence"] = float(metrics.global_confidence) if metrics.global_confidence else 0.0
        response_data["llm_used"] = metrics.llm_used if metrics.llm_used else False
        response_data["model_used"] = metrics.model_used
        response_data["pub_count"] = len(publications)
        response_data["metrics"] = {
            "applicant_id": applicant_id,
            "bsc_uni_name": metrics.bsc_uni_name,
            "bsc_qs_rank": metrics.bsc_qs_rank,
            "bsc_gpa_raw": float(metrics.bsc_gpa_raw) if metrics.bsc_gpa_raw else None,
            "bsc_gpa_scale": float(metrics.bsc_gpa_scale) if metrics.bsc_gpa_scale else None,
            "bsc_gpa_normalised": float(metrics.bsc_gpa_normalised) if metrics.bsc_gpa_normalised else None,
            "msc_uni_name": metrics.msc_uni_name,
            "msc_qs_rank": metrics.msc_qs_rank,
            "msc_gpa_raw": float(metrics.msc_gpa_raw) if metrics.msc_gpa_raw else None,
            "msc_gpa_scale": float(metrics.msc_gpa_scale) if metrics.msc_gpa_scale else None,
            "msc_gpa_normalised": float(metrics.msc_gpa_normalised) if metrics.msc_gpa_normalised else None,
            "msc_absent": metrics.msc_absent if metrics.msc_absent else False,
            "global_confidence": float(metrics.global_confidence) if metrics.global_confidence else 0.0,
            "llm_used": metrics.llm_used if metrics.llm_used else False,
            "extraction_source_detail": metrics.extraction_source_detail,
            "model_used": metrics.model_used,
            "extracted_at": metrics.extracted_at
        }
    else:
        response_data["pub_count"] = 0
        response_data["metrics"] = None
    
    return ApplicantDetail(**response_data)


@router.patch("/applicants/{applicant_id}/metrics")
async def update_metrics(
    applicant_id: uuid.UUID,
    updated_data: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    # Mise à jour Identité
    applicant = await get_applicant(db, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    identity_fields = ["full_name", "email", "nationality", "needs_human_review"]
    for field in identity_fields:
        if field in updated_data:
            setattr(applicant, field, updated_data[field])

    # Mise à jour Métriques
    result = await db.execute(
        select(ExtractedMetrics).where(ExtractedMetrics.applicant_id == applicant_id)
    )
    db_metrics = result.scalar_one_or_none()
    if not db_metrics:
        db_metrics = ExtractedMetrics(applicant_id=applicant_id)
        db.add(db_metrics)

    metrics_fields = [
        "bsc_uni_name", "bsc_qs_rank", "bsc_gpa_raw", "bsc_gpa_scale", "bsc_gpa_normalised",
        "msc_uni_name", "msc_qs_rank", "msc_gpa_raw", "msc_gpa_scale", "msc_gpa_normalised",
        "msc_absent", "global_confidence"
    ]
    for key, value in updated_data.items():
        if key in metrics_fields and hasattr(db_metrics, key):
            setattr(db_metrics, key, value)

    await db.commit()
    return {"status": "success"}


# ============================================================================
# PUBLICATION ENDPOINTS
# ============================================================================

@router.get("/applicants/{applicant_id}/publications")
async def get_applicant_publications(
    applicant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Récupère toutes les publications d'un candidat."""
    publications = await list_publications(db, applicant_id)
    result = []
    for pub in publications:
        result.append({
            "id": str(pub.id),
            "title": pub.title,
            "year": pub.year,
            "pub_type": pub.pub_type,
            "authors_raw": pub.authors_raw,
            "author_position": pub.author_position,
            "total_authors": pub.total_authors,
            "contribution_score": float(pub.contribution_score) if pub.contribution_score else None,
            "venue_name": pub.venue.name if pub.venue else None
        })
    return result


@router.put("/publications/{publication_id}")
async def update_publication_endpoint(
    publication_id: uuid.UUID,
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Met à jour une publication existante."""
    pub = await get_publication(db, publication_id)
    if not pub:
        raise HTTPException(404, "Publication not found")
    
    allowed_fields = ["title", "year", "pub_type", "authors_raw", 
                      "author_position", "total_authors", "contribution_score"]
    
    update_data = {}
    for field in allowed_fields:
        if field in data and data[field] is not None:
            update_data[field] = data[field]
    
    if "venue" in data and data["venue"]:
        result = await db.execute(
            select(Venue).where(
                Venue.name == data["venue"],
                Venue.venue_type == data.get("pub_type", pub.pub_type)
            )
        )
        venue = result.scalar_one_or_none()
        if not venue:
            venue = Venue(
                name=data["venue"],
                venue_type=data.get("pub_type", pub.pub_type)
            )
            db.add(venue)
            await db.flush()
        update_data["venue_id"] = venue.id
    
    await update_publication(db, publication_id, update_data)
    await db.commit()
    
    return {"message": "Publication updated successfully"}


@router.delete("/publications/{publication_id}")
async def delete_publication_endpoint(
    publication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Supprime une publication."""
    success = await delete_publication(db, publication_id)
    if not success:
        raise HTTPException(404, "Publication not found")
    
    await db.commit()
    return {"message": "Publication deleted successfully"}


@router.post("/publications", status_code=status.HTTP_201_CREATED)
async def create_publication(
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Ajoute une nouvelle publication à un candidat."""
    from backend.app.db.repositories.publication_repo import create_publication
    
    applicant_id = data.get("applicant_id")
    if not applicant_id:
        raise HTTPException(400, "applicant_id is required")
    
    applicant = await get_applicant(db, uuid.UUID(applicant_id))
    if not applicant:
        raise HTTPException(404, "Applicant not found")
    
    venue_id = None
    if "venue" in data and data["venue"]:
        result = await db.execute(
            select(Venue).where(
                Venue.name == data["venue"],
                Venue.venue_type == data.get("pub_type", "journal")
            )
        )
        venue = result.scalar_one_or_none()
        if not venue:
            venue = Venue(
                name=data["venue"],
                venue_type=data.get("pub_type", "journal")
            )
            db.add(venue)
            await db.flush()
        venue_id = venue.id
    
    pub = await create_publication(
        db=db,
        applicant_id=uuid.UUID(applicant_id),
        venue_id=venue_id,
        pub_type=data.get("pub_type", "journal"),
        position_in_cv=999,
        title=data.get("title"),
        authors_raw=data.get("authors_raw"),
        author_position=data.get("author_position"),
        total_authors=data.get("total_authors"),
        contribution_score=data.get("contribution_score", 0.5),
        year=data.get("year"),
        extraction_source="manual"
    )
    
    await db.commit()
    return {"id": str(pub.id), "message": "Publication created successfully"}