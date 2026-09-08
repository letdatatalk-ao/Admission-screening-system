import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, ExtractedMetrics, Publication, Venue
from backend.app.db.repositories.applicant_repo import (
    get_applicant, get_extracted_metrics, list_applicants
)
from backend.app.db.repositories.publication_repo import list_publications, get_publication, update_publication, delete_publication
from backend.app.db.repositories.scoring_repo import log_action, save_manual_override
from backend.app.api.v1.schemas import (
    ApplicantRead, ApplicantDetail,
    MetricsPatchRequest, PublicationUpdateRequest, PublicationCreateRequest,
)
from backend.app.api.v1.auth import check_evaluator

router = APIRouter(tags=["Applicants"])


@router.get("/applicants", response_model=List[ApplicantRead])
async def get_applicants_list(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
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
            Applicant.retry_count,
            Applicant.last_error,
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
            "retry_count": row["retry_count"],
            "last_error": row["last_error"],
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


def _f(val):
    return float(val) if val is not None else None


@router.get("/applicants/{applicant_id}", response_model=ApplicantDetail)
async def get_applicant_details(
    applicant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    applicant = await get_applicant(db, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    metrics = await get_extracted_metrics(db, applicant_id)
    publications = await list_publications(db, applicant_id)

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
            "contribution_score": _f(pub.contribution_score) or 0.0,
            "scopus_pct_at_extraction": _f(pub.scopus_pct_at_extraction),
            "core_score_at_extraction": pub.core_score_at_extraction,
            "doi": pub.doi if hasattr(pub, 'doi') else None,
            "venue_name": pub.venue.name if pub.venue else None,
        }
        pubs_with_venue.append(pub_dict)

    response_data = {
        "id": str(applicant.id),
        "application_ref": applicant.application_ref,
        "full_name": applicant.full_name,
        "email": applicant.email,
        "nationality": applicant.nationality,
        "phone": applicant.phone if hasattr(applicant, 'phone') else None,
        "linkedin": applicant.linkedin if hasattr(applicant, 'linkedin') else None,
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

    if metrics:
        response_data.update({
            "bsc_uni_name": metrics.bsc_uni_name,
            "bsc_qs_rank": metrics.bsc_qs_rank,
            "bsc_gpa_raw": _f(metrics.bsc_gpa_raw),
            "bsc_gpa_scale": _f(metrics.bsc_gpa_scale),
            "bsc_gpa_normalised": _f(metrics.bsc_gpa_normalised),
            "msc_uni_name": metrics.msc_uni_name,
            "msc_qs_rank": metrics.msc_qs_rank,
            "msc_gpa_raw": _f(metrics.msc_gpa_raw),
            "msc_gpa_scale": _f(metrics.msc_gpa_scale),
            "msc_gpa_normalised": _f(metrics.msc_gpa_normalised),
            "msc_absent": metrics.msc_absent if metrics.msc_absent else False,
            "global_confidence": _f(metrics.global_confidence) or 0.0,
            "llm_used": metrics.llm_used if metrics.llm_used else False,
            "model_used": metrics.model_used,
            "pub_count": len(publications),
            "metrics": {
                "applicant_id": str(applicant_id),
                # BSc
                "bsc_uni_name": metrics.bsc_uni_name,
                "bsc_qs_rank": metrics.bsc_qs_rank,
                "bsc_gpa_raw": _f(metrics.bsc_gpa_raw),
                "bsc_gpa_scale": _f(metrics.bsc_gpa_scale),
                "bsc_gpa_normalised": _f(metrics.bsc_gpa_normalised),
                "bsc_field": metrics.bsc_field if hasattr(metrics, 'bsc_field') else None,
                "bsc_country": metrics.bsc_country if hasattr(metrics, 'bsc_country') else None,
                "bsc_year": metrics.bsc_year if hasattr(metrics, 'bsc_year') else None,
                # MSc
                "msc_uni_name": metrics.msc_uni_name,
                "msc_qs_rank": metrics.msc_qs_rank,
                "msc_gpa_raw": _f(metrics.msc_gpa_raw),
                "msc_gpa_scale": _f(metrics.msc_gpa_scale),
                "msc_gpa_normalised": _f(metrics.msc_gpa_normalised),
                "msc_absent": metrics.msc_absent if metrics.msc_absent else False,
                "msc_field": metrics.msc_field if hasattr(metrics, 'msc_field') else None,
                "msc_country": metrics.msc_country if hasattr(metrics, 'msc_country') else None,
                "msc_year": metrics.msc_year if hasattr(metrics, 'msc_year') else None,
                # PhD
                "phd_uni_name": metrics.phd_uni_name if hasattr(metrics, 'phd_uni_name') else None,
                "phd_field": metrics.phd_field if hasattr(metrics, 'phd_field') else None,
                "phd_year": metrics.phd_year if hasattr(metrics, 'phd_year') else None,
                "phd_qs_rank": metrics.phd_qs_rank if hasattr(metrics, 'phd_qs_rank') else None,
                # Test scores
                "gre_verbal": metrics.gre_verbal if hasattr(metrics, 'gre_verbal') else None,
                "gre_quant": metrics.gre_quant if hasattr(metrics, 'gre_quant') else None,
                "gre_awa": _f(metrics.gre_awa) if hasattr(metrics, 'gre_awa') else None,
                "ielts_score": _f(metrics.ielts_score) if hasattr(metrics, 'ielts_score') else None,
                "toefl_score": metrics.toefl_score if hasattr(metrics, 'toefl_score') else None,
                # Professional
                "work_exp_years": _f(metrics.work_exp_years) if hasattr(metrics, 'work_exp_years') else None,
                # Research
                "research_interests": metrics.research_interests if hasattr(metrics, 'research_interests') else None,
                "awards": metrics.awards if hasattr(metrics, 'awards') else None,
                # Meta
                "global_confidence": _f(metrics.global_confidence) or 0.0,
                "llm_used": metrics.llm_used if metrics.llm_used else False,
                "extraction_source_detail": metrics.extraction_source_detail,
                "model_used": metrics.model_used,
                "extracted_at": metrics.extracted_at,
            }
        })
    else:
        response_data["pub_count"] = 0
        response_data["metrics"] = None

    return ApplicantDetail(**response_data)


@router.patch("/applicants/{applicant_id}/metrics")
async def update_metrics(
    applicant_id: uuid.UUID,
    updated_data: MetricsPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    applicant = await get_applicant(db, applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    identity_fields = ["full_name", "email", "nationality", "needs_human_review", "phone", "linkedin"]
    payload = updated_data.model_dump(exclude_none=True)
    review_reason = payload.pop("review_reason", None)

    result = await db.execute(
        select(ExtractedMetrics).where(ExtractedMetrics.applicant_id == applicant_id)
    )
    db_metrics = result.scalar_one_or_none()
    if not db_metrics:
        db_metrics = ExtractedMetrics(applicant_id=applicant_id)
        db.add(db_metrics)
        await db.flush()  # populate db_metrics.id for the override records below

    metrics_fields = {
        "bsc_uni_name", "bsc_qs_rank", "bsc_gpa_raw", "bsc_gpa_scale", "bsc_gpa_normalised",
        "bsc_field", "bsc_country", "bsc_year",
        "msc_uni_name", "msc_qs_rank", "msc_gpa_raw", "msc_gpa_scale", "msc_gpa_normalised",
        "msc_absent", "msc_field", "msc_country", "msc_year",
        "phd_uni_name", "phd_field", "phd_year", "phd_qs_rank",
        "gre_verbal", "gre_quant", "gre_awa", "ielts_score", "toefl_score",
        "work_exp_years", "research_interests", "awards",
        "global_confidence",
    }

    # Snapshot of what's actually changing, for the audit trail — captured
    # before any setattr so old_state reflects the pre-edit record.
    old_state: dict = {}
    new_state: dict = {}
    for field in identity_fields:
        if field in payload:
            old_state[field] = getattr(applicant, field, None)
            new_state[field] = payload[field]
            setattr(applicant, field, payload[field])
    for key, value in payload.items():
        if key in metrics_fields and hasattr(db_metrics, key):
            old_state[key] = getattr(db_metrics, key, None)
            new_state[key] = value
            setattr(db_metrics, key, value)

    if new_state:
        await log_action(
            db,
            action_type="MANUAL_CORRECTION",
            session_id=applicant.session_id,
            user_id=current_user.get("id"),
            entity_type="applicant",
            entity_id=applicant_id,
            old_state={**old_state, "reason": review_reason},
            new_state={**new_state, "reason": review_reason},
        )
        # Per-field record in manual_overrides, in addition to the single
        # audit_log entry above — save_manual_override()'s own docstring
        # says it's meant to be called from exactly this Review-page save
        # action, but nothing here ever actually called it.
        for field in identity_fields:
            if field in payload:
                await save_manual_override(
                    db,
                    applicant_id=applicant_id,
                    table_name="applicants",
                    record_id=applicant_id,
                    field_name=field,
                    old_value=None if old_state.get(field) is None else str(old_state[field]),
                    new_value=str(new_state[field]),
                    overridden_by=current_user.get("id"),
                    reason=review_reason,
                )
        for key in metrics_fields:
            if key in new_state:
                await save_manual_override(
                    db,
                    applicant_id=applicant_id,
                    table_name="extracted_metrics",
                    record_id=db_metrics.id,
                    field_name=key,
                    old_value=None if old_state.get(key) is None else str(old_state[key]),
                    new_value=str(new_state[key]),
                    overridden_by=current_user.get("id"),
                    reason=review_reason,
                )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving metrics.")
    return {"status": "success"}


# ============================================================================
# PUBLICATION ENDPOINTS
# ============================================================================

@router.get("/applicants/{applicant_id}/publications")
async def get_applicant_publications(
    applicant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
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
            "contribution_score": _f(pub.contribution_score),
            "scopus_pct_at_extraction": _f(pub.scopus_pct_at_extraction),
            "core_score_at_extraction": pub.core_score_at_extraction,
            "doi": pub.doi if hasattr(pub, 'doi') else None,
            "venue_name": pub.venue.name if pub.venue else None,
        })
    return result


@router.put("/publications/{publication_id}")
async def update_publication_endpoint(
    publication_id: uuid.UUID,
    data: PublicationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    pub = await get_publication(db, publication_id)
    if not pub:
        raise HTTPException(404, "Publication not found")

    payload = data.model_dump(exclude_none=True)
    venue_name = payload.pop("venue", None)

    update_data = {k: v for k, v in payload.items()}

    if venue_name:
        result = await db.execute(
            select(Venue).where(
                Venue.name == venue_name,
                Venue.venue_type == (payload.get("pub_type") or pub.pub_type)
            )
        )
        venue = result.scalar_one_or_none()
        if not venue:
            venue = Venue(
                name=venue_name,
                venue_type=payload.get("pub_type") or pub.pub_type
            )
            db.add(venue)
            await db.flush()
        update_data["venue_id"] = venue.id

    await update_publication(db, publication_id, update_data)
    owner = await get_applicant(db, pub.applicant_id)
    await log_action(
        db, action_type="PUBLICATION_CORRECTION", session_id=owner.session_id if owner else None,
        user_id=current_user.get("id"), entity_type="publication", entity_id=publication_id,
        new_state=update_data,
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while updating publication.")

    return {"message": "Publication updated successfully"}


@router.delete("/publications/{publication_id}")
async def delete_publication_endpoint(
    publication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    pub = await get_publication(db, publication_id)
    if not pub:
        raise HTTPException(404, "Publication not found")
    owner = await get_applicant(db, pub.applicant_id)
    applicant_id, session_id = pub.applicant_id, (owner.session_id if owner else None)

    success = await delete_publication(db, publication_id)
    if not success:
        raise HTTPException(404, "Publication not found")

    await log_action(
        db, action_type="PUBLICATION_DELETED", session_id=session_id,
        user_id=current_user.get("id"), entity_type="publication", entity_id=publication_id,
        old_state={"applicant_id": str(applicant_id), "title": pub.title},
    )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while deleting publication.")
    return {"message": "Publication deleted successfully"}


@router.post("/publications", status_code=status.HTTP_201_CREATED)
async def create_publication(
    data: PublicationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    from backend.app.db.repositories.publication_repo import create_publication as _create_pub

    applicant = await get_applicant(db, data.applicant_id)
    if not applicant:
        raise HTTPException(404, "Applicant not found")

    venue_id = None
    if data.venue:
        result = await db.execute(
            select(Venue).where(
                Venue.name == data.venue,
                Venue.venue_type == data.pub_type
            )
        )
        venue = result.scalar_one_or_none()
        if not venue:
            venue = Venue(name=data.venue, venue_type=data.pub_type)
            db.add(venue)
            await db.flush()
        venue_id = venue.id

    pub = await _create_pub(
        db=db,
        applicant_id=data.applicant_id,
        venue_id=venue_id,
        pub_type=data.pub_type,
        position_in_cv=999,
        title=data.title,
        authors_raw=data.authors_raw,
        author_position=data.author_position,
        total_authors=data.total_authors,
        contribution_score=data.contribution_score,
        year=data.year,
        extraction_source="manual"
    )

    await log_action(
        db, action_type="PUBLICATION_CREATED", session_id=applicant.session_id,
        user_id=current_user.get("id"), entity_type="publication", entity_id=pub.id,
        new_state={"title": data.title, "pub_type": data.pub_type},
    )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error while creating publication.")
    return {"id": str(pub.id), "message": "Publication created successfully"}
