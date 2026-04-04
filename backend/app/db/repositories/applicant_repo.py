"""
backend/app/db/repositories/applicant_repo.py

CRUD pour Applicant et ExtractedMetrics.
Remplace/complète le fichier existant en s'appuyant sur models.py.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Applicant, ExtractedMetrics


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
    """Crée un candidat dans une session d'évaluation."""
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
    db:         AsyncSession,
    session_id: uuid.UUID,
    status:     Optional[str] = None,      # "pending" | "processed" | "error"
    needs_review: Optional[bool] = None,
) -> list[Applicant]:
    """Liste les candidats d'une session avec filtres optionnels."""
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
    """Met à jour le statut de traitement d'un candidat."""
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
    """Lie les documents uploadés au candidat et marque le pairing complet."""
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
    """
    Met à jour le dernier score composite et le rang du candidat.
    Appelé par scoring_repo après chaque run de ranking.
    """
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
    """Active ou désactive le flag needs_human_review."""
    await db.execute(
        update(Applicant)
        .where(Applicant.id == applicant_id)
        .values(needs_human_review=flag)
    )


# ---------------------------------------------------------------------------
# ExtractedMetrics
# ---------------------------------------------------------------------------

async def upsert_extracted_metrics(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
    data:         dict,
) -> ExtractedMetrics:
    """
    Crée ou met à jour les métriques extraites pour un candidat.
    `data` est un dict dont les clés correspondent aux colonnes d'ExtractedMetrics.

    Exemple de `data` produit par le pipeline NLP + fusion :
    {
        "bsc_uni_name":        "AlHosn University",
        "bsc_qs_rank":         None,
        "bsc_qs_normalised":   0.150,
        "bsc_gpa_raw":         3.50,
        "bsc_gpa_scale":       4.0,
        "bsc_gpa_normalised":  3.500,
        "bsc_gpa_source":      "explicit_scale",
        "msc_uni_name":        "New York University",
        "msc_qs_rank":         32,
        "msc_qs_normalised":   0.972,
        "msc_gpa_raw":         3.80,
        "msc_gpa_scale":       4.0,
        "msc_gpa_normalised":  3.800,
        "msc_gpa_source":      "explicit_scale",
        "global_confidence":   0.85,
        "nlp_confidence_detail": {...},
        "llm_used":            True,
        "model_used":          "mistral:7b-instruct",
    }
    """
    # Cherche si une ligne existe déjà (unique sur applicant_id)
    result = await db.execute(
        select(ExtractedMetrics).where(
            ExtractedMetrics.applicant_id == applicant_id
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # UPDATE — on écrase avec les nouvelles valeurs
        await db.execute(
            update(ExtractedMetrics)
            .where(ExtractedMetrics.applicant_id == applicant_id)
            .values(**data)
        )
        await db.flush()
        result2 = await db.execute(
            select(ExtractedMetrics).where(
                ExtractedMetrics.applicant_id == applicant_id
            )
        )
        return result2.scalar_one()
    else:
        # INSERT
        metrics = ExtractedMetrics(applicant_id=applicant_id, **data)
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