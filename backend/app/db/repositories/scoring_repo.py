"""
backend/app/db/repositories/scoring_repo.py

Persistance des résultats de scoring, overrides manuels et audit log.
Tables : ranking_results, manual_overrides, audit_log.
"""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import RankingResult, ManualOverride, AuditLog
from backend.app.db.repositories.applicant_repo import update_applicant_score


# ---------------------------------------------------------------------------
# RankingResult
# ---------------------------------------------------------------------------

async def save_ranking_result(
    db:               AsyncSession,
    session_id:       uuid.UUID,
    config_id:        uuid.UUID,
    total_applicants: int,
    scores_snapshot:  list[dict],
    computed_by:      Optional[uuid.UUID] = None,
) -> RankingResult:
    """
    Persiste un run de ranking complet en base.

    `scores_snapshot` est la liste des RankedResult sérialisés — stockée
    en JSONB pour un accès rapide sans rejoindre toutes les tables.

    Format attendu de chaque entrée dans scores_snapshot :
    {
        "rank":           1,
        "applicant_id":   "uuid-str",
        "applicant_name": "Esra Al-Nashash",
        "final_score":    78.40,
        "bsc_academic":   82.0,
        "msc_academic":   91.5,
        "journal_score":  65.0,
        "conf_score":     50.0,
        "needs_review":   False,
        "missing_fields": [],
        "tiebreak_used":  None,
    }
    """
    result = RankingResult(
        session_id=session_id,
        config_id=config_id,
        total_applicants=total_applicants,
        scores_snapshot=scores_snapshot,
        computed_by=computed_by,
    )
    db.add(result)
    await db.flush()
    await db.refresh(result)
    return result


async def save_ranking_and_update_applicants(
    db:              AsyncSession,
    session_id:      uuid.UUID,
    config_id:       uuid.UUID,
    ranked_results:  list[dict],
    computed_by:     Optional[uuid.UUID] = None,
) -> RankingResult:
    """
    Opération atomique : persiste le RankingResult ET met à jour
    last_composite_score + last_rank sur chaque Applicant.

    `ranked_results` : liste de dicts avec les champs de RankedResult.

    Appelé depuis FastAPI après compute_scores_batch() + rank().
    La transaction est gérée par le contexte FastAPI (commit en fin de requête).
    """
    # 1. Sauvegarder le snapshot global
    ranking = await save_ranking_result(
        db=db,
        session_id=session_id,
        config_id=config_id,
        total_applicants=len(ranked_results),
        scores_snapshot=ranked_results,
        computed_by=computed_by,
    )

    # 2. Mettre à jour chaque candidat individuellement
    for r in ranked_results:
        applicant_id = uuid.UUID(r["applicant_id"]) if isinstance(
            r["applicant_id"], str) else r["applicant_id"]
        await update_applicant_score(
            db=db,
            applicant_id=applicant_id,
            composite_score=r["final_score"],
            rank=r["rank"],
            config_id=config_id,
            needs_review=r.get("needs_review", False),
        )

    return ranking


async def get_latest_ranking(
    db:         AsyncSession,
    session_id: uuid.UUID,
) -> Optional[RankingResult]:
    """Retourne le dernier run de ranking pour une session."""
    result = await db.execute(
        select(RankingResult)
        .where(RankingResult.session_id == session_id)
        .order_by(RankingResult.computed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_ranking_history(
    db:         AsyncSession,
    session_id: uuid.UUID,
) -> list[RankingResult]:
    """Retourne l'historique complet des runs de ranking pour une session."""
    result = await db.execute(
        select(RankingResult)
        .where(RankingResult.session_id == session_id)
        .order_by(RankingResult.computed_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# ManualOverride
# ---------------------------------------------------------------------------

async def save_manual_override(
    db:             AsyncSession,
    applicant_id:   uuid.UUID,
    table_name:     str,
    record_id:      uuid.UUID,
    field_name:     str,
    new_value:      str,
    overridden_by:  uuid.UUID,
    old_value:      Optional[str] = None,
    reason:         Optional[str] = None,
) -> ManualOverride:
    """
    Enregistre une correction manuelle d'un champ extrait.

    Appelé quand un évaluateur corrige via l'UI Streamlit (page Review).
    Exemple : corriger bsc_gpa_normalised de 0.725 à 0.800.

    table_name : "extracted_metrics" | "publications"
    record_id  : ID de la ligne modifiée
    field_name : nom de la colonne corrigée
    """
    override = ManualOverride(
        applicant_id=applicant_id,
        table_name=table_name,
        record_id=record_id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        overridden_by=overridden_by,
    )
    db.add(override)
    await db.flush()
    await db.refresh(override)
    return override


async def list_overrides(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
) -> list[ManualOverride]:
    """Retourne toutes les corrections manuelles pour un candidat."""
    result = await db.execute(
        select(ManualOverride)
        .where(ManualOverride.applicant_id == applicant_id)
        .order_by(ManualOverride.overridden_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

def _json_safe(value):
    """
    Recursively convert values pulled straight off SQLAlchemy ORM attributes
    (Decimal from Numeric columns, datetime/date, UUID) into JSON-native
    types. old_state/new_state snapshots are built with getattr() on live
    model instances, so callers routinely hand log_action a Decimal (e.g.
    bsc_gpa_normalised, global_confidence) — the JSONB column's json.dumps
    has no idea how to encode that and raises TypeError, which previously
    surfaced as a 500 on every correction touching a numeric field, with
    the underlying DB write already flushed but the audit entry lost.
    """
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


async def log_action(
    db:           AsyncSession,
    action_type:  str,
    session_id:   Optional[uuid.UUID] = None,
    user_id:      Optional[uuid.UUID] = None,
    entity_type:  Optional[str]       = None,
    entity_id:    Optional[uuid.UUID] = None,
    old_state:    Optional[dict]      = None,
    new_state:    Optional[dict]      = None,
    ip_address:   Optional[str]       = None,
) -> AuditLog:
    """
    Écrit une entrée dans l'audit log.

    action_type exemples :
        "upload_cv"          — upload d'un CV
        "upload_transcript"  — upload d'un transcript
        "extraction_done"    — pipeline NLP terminé
        "ranking_computed"   — run de scoring terminé
        "manual_override"    — correction manuelle
        "session_closed"     — session fermée

    Appelé depuis FastAPI après chaque action significative.
    """
    old_state = _json_safe(old_state) if old_state is not None else None
    new_state = _json_safe(new_state) if new_state is not None else None
    entry = AuditLog(
        session_id=session_id,
        user_id=user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        old_state=old_state,
        new_state=new_state,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_audit_trail(
    db:          AsyncSession,
    session_id:  Optional[uuid.UUID] = None,
    entity_type: Optional[str]       = None,
    entity_id:   Optional[uuid.UUID] = None,
    limit:       int                 = 100,
) -> list[AuditLog]:
    """Retourne l'historique d'audit filtré."""
    q = select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit)
    if session_id:
        q = q.where(AuditLog.session_id == session_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    result = await db.execute(q)
    return list(result.scalars().all())