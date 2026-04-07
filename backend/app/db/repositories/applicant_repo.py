"""
backend/app/db/repositories/applicant_repo.py

CRUD pour Applicant et ExtractedMetrics.
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional
from datetime import datetime

from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from backend.app.db.models import Applicant, ExtractedMetrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Applicant
# ---------------------------------------------------------------------------

async def create_applicant(
    db:              AsyncSession,
    session_id:      uuid.UUID,
    application_ref: str,
    full_name:       str,
    email:           Optional[str] = None,
    nationality:     Optional[str] = None,
) -> Applicant:
    applicant = Applicant(
        session_id=session_id,
        application_ref=application_ref,
        full_name=full_name,
        email=email,
        nationality=nationality,
        status="pending",
        needs_human_review=False,
        pairing_complete=False,
    )
    db.add(applicant)
    await db.flush()
    await db.refresh(applicant)
    return applicant


async def get_applicant(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
) -> Optional[Applicant]:
    result = await db.execute(
        select(Applicant).where(Applicant.id == applicant_id)
    )
    return result.scalar_one_or_none()


async def get_applicant_by_ref(
    db:              AsyncSession,
    application_ref: str,
) -> Optional[Applicant]:
    result = await db.execute(
        select(Applicant).where(Applicant.application_ref == application_ref)
    )
    return result.scalar_one_or_none()


async def list_applicants(
    db:           AsyncSession,
    session_id:   uuid.UUID,
    status:       Optional[str] = None,
    needs_review: Optional[bool] = None,
) -> list[Applicant]:
    q = select(Applicant).where(Applicant.session_id == session_id)
    if status is not None:
        q = q.where(Applicant.status == status)
    if needs_review is not None:
        q = q.where(Applicant.needs_human_review == needs_review)
    q = q.order_by(Applicant.last_rank.asc().nulls_last())
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_applicant_status(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
    status:       str,
) -> None:
    await db.execute(
        update(Applicant)
        .where(Applicant.id == applicant_id)
        .values(status=status)
    )


async def update_applicant_documents(
    db:                     AsyncSession,
    applicant_id:           uuid.UUID,
    cv_document_id:         Optional[uuid.UUID] = None,
    transcript_document_id: Optional[uuid.UUID] = None,
) -> None:
    values: dict = {}
    if cv_document_id is not None:
        values["cv_document_id"] = cv_document_id
    if transcript_document_id is not None:
        values["transcript_document_id"] = transcript_document_id
    if cv_document_id and transcript_document_id:
        values["pairing_complete"] = True
    if values:
        await db.execute(
            update(Applicant).where(Applicant.id == applicant_id).values(**values)
        )


async def update_applicant_score(
    db:               AsyncSession,
    applicant_id:     uuid.UUID,
    composite_score:  float,
    rank:             int,
    config_id:        uuid.UUID,
    needs_review:     bool = False,
) -> None:
    await db.execute(
        update(Applicant)
        .where(Applicant.id == applicant_id)
        .values(
            last_composite_score=round(composite_score, 3),
            last_rank=rank,
            last_ranking_config_id=config_id,
            needs_human_review=needs_review,
            status="processed",
        )
    )


async def flag_review(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
    flag:         bool = True,
) -> None:
    await db.execute(
        update(Applicant)
        .where(Applicant.id == applicant_id)
        .values(needs_human_review=flag)
    )


# ---------------------------------------------------------------------------
# Gestion des reprises (retry)
# ---------------------------------------------------------------------------

async def increment_retry_count(
    db:            AsyncSession,
    applicant_id:  uuid.UUID,
    error_message: Optional[str] = None,
) -> None:
    """Incrémente le compteur de tentatives et enregistre l'erreur."""
    await db.execute(
        update(Applicant)
        .where(Applicant.id == applicant_id)
        .values(
            retry_count=Applicant.retry_count + 1,
            last_error=error_message,
            last_attempt_at=func.now(),
            status="error"
        )
    )


async def reset_retry_count(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
) -> None:
    """Réinitialise le compteur de tentatives après un succès."""
    await db.execute(
        update(Applicant)
        .where(Applicant.id == applicant_id)
        .values(
            retry_count=0,
            last_error=None,
            status="processed"
        )
    )


async def get_pending_applicants(
    db:         AsyncSession,
    session_id: uuid.UUID,
    max_retry: int = 5,
) -> list[Applicant]:
    """Récupère les CV à traiter (pending ou error avec retry_count < max_retry)."""
    result = await db.execute(
        select(Applicant)
        .where(Applicant.session_id == session_id)
        .where(
            or_(
                Applicant.status == "pending",
                and_(
                    Applicant.status == "error",
                    Applicant.retry_count < max_retry
                )
            )
        )
        .order_by(Applicant.retry_count.asc(), Applicant.created_at.asc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# ExtractedMetrics
# ---------------------------------------------------------------------------

_VALID_METRICS_COLUMNS = {
    "applicant_id", "cv_document_id", "transcript_document_id",
    "bsc_uni_name", "bsc_qs_rank", "bsc_qs_normalised",
    "bsc_gpa_raw", "bsc_gpa_scale", "bsc_gpa_normalised",
    "bsc_gpa_normalised_done", "bsc_gpa_source",
    "msc_uni_name", "msc_qs_rank", "msc_qs_normalised",
    "msc_gpa_raw", "msc_gpa_scale", "msc_gpa_normalised",
    "msc_gpa_normalised_done", "msc_gpa_source", "msc_absent",
    "global_confidence", "nlp_confidence_detail",
    "llm_used", "llm_confidence_detail", "extraction_source_detail",
    "model_used", "extracted_at"
}


async def upsert_extracted_metrics(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
    data:         dict,
) -> ExtractedMetrics:
    filtered_data = {k: v for k, v in data.items() if k in _VALID_METRICS_COLUMNS}
    
    ignored_keys = set(data.keys()) - set(filtered_data.keys())
    if ignored_keys:
        logger.warning(f"Ignored invalid fields for ExtractedMetrics: {ignored_keys}")
    
    result = await db.execute(
        select(ExtractedMetrics).where(
            ExtractedMetrics.applicant_id == applicant_id
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        await db.execute(
            update(ExtractedMetrics)
            .where(ExtractedMetrics.applicant_id == applicant_id)
            .values(**filtered_data)
        )
        await db.flush()
        result2 = await db.execute(
            select(ExtractedMetrics).where(
                ExtractedMetrics.applicant_id == applicant_id
            )
        )
        return result2.scalar_one()
    else:
        metrics = ExtractedMetrics(applicant_id=applicant_id, **filtered_data)
        db.add(metrics)
        await db.flush()
        await db.refresh(metrics)
        return metrics


async def get_extracted_metrics(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
) -> Optional[ExtractedMetrics]:
    result = await db.execute(
        select(ExtractedMetrics).where(
            ExtractedMetrics.applicant_id == applicant_id
        )
    )
    return result.scalar_one_or_none()