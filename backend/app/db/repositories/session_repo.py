"""
backend/app/db/repositories/session_repo.py

CRUD pour EvaluationSession et RankingConfig.
Toutes les fonctions reçoivent une AsyncSession SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import EvaluationSession, RankingConfig


# ---------------------------------------------------------------------------
# EvaluationSession
# ---------------------------------------------------------------------------

async def create_session(
    db:            AsyncSession,
    name:          str,
    academic_year: str,
    qs_year:       int,
    created_by:    Optional[uuid.UUID] = None,
) -> EvaluationSession:
    """Crée une nouvelle session d'évaluation."""
    session = EvaluationSession(
        name=name,
        academic_year=academic_year,
        qs_year=qs_year,
        status="active",
        created_by=created_by,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_session(
    db:         AsyncSession,
    session_id: uuid.UUID,
) -> Optional[EvaluationSession]:
    """Retourne une session par ID, ou None si inexistante."""
    result = await db.execute(
        select(EvaluationSession).where(EvaluationSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def list_sessions(
    db:     AsyncSession,
    status: Optional[str] = None,   # "active" | "closed" | None (tous)
) -> list[EvaluationSession]:
    """Liste toutes les sessions, filtrées par statut si fourni."""
    q = select(EvaluationSession).order_by(EvaluationSession.created_at.desc())
    if status:
        q = q.where(EvaluationSession.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def close_session(
    db:         AsyncSession,
    session_id: uuid.UUID,
) -> Optional[EvaluationSession]:
    """Passe une session en statut 'closed' et enregistre closed_at."""
    await db.execute(
        update(EvaluationSession)
        .where(EvaluationSession.id == session_id)
        .values(
            status="closed",
            closed_at=datetime.now(timezone.utc),
        )
    )
    return await get_session(db, session_id)


# ---------------------------------------------------------------------------
# RankingConfig
# ---------------------------------------------------------------------------

async def create_ranking_config(
    db:             AsyncSession,
    session_id:     uuid.UUID,
    name:           str,
    weights:        dict,               # {"w_bsc": 15, "w_msc": 25, ...}
    is_default:     bool = False,
    tiebreak_field: Optional[str] = None,
    created_by:     Optional[uuid.UUID] = None,
) -> RankingConfig:
    """
    Crée une configuration de poids pour une session.

    weights doit contenir les clés : w_bsc, w_msc, w_jour, w_conf
    La somme doit être 100 — la validation est faite côté engine.py.
    """
    # Si is_default, on retire le flag des autres configs de la session
    if is_default:
        await db.execute(
            update(RankingConfig)
            .where(RankingConfig.session_id == session_id)
            .values(is_default=False)
        )

    config = RankingConfig(
        session_id=session_id,
        name=name,
        weights=weights,
        is_default=is_default,
        tiebreak_field=tiebreak_field,
        created_by=created_by,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


async def get_ranking_config(
    db:        AsyncSession,
    config_id: uuid.UUID,
) -> Optional[RankingConfig]:
    result = await db.execute(
        select(RankingConfig).where(RankingConfig.id == config_id)
    )
    return result.scalar_one_or_none()


async def get_default_config(
    db:         AsyncSession,
    session_id: uuid.UUID,
) -> Optional[RankingConfig]:
    """Retourne la config marquée is_default pour cette session."""
    result = await db.execute(
        select(RankingConfig).where(
            RankingConfig.session_id == session_id,
            RankingConfig.is_default == True,
        )
    )
    return result.scalar_one_or_none()


async def list_configs(
    db:         AsyncSession,
    session_id: uuid.UUID,
) -> list[RankingConfig]:
    """Liste toutes les configs d'une session."""
    result = await db.execute(
        select(RankingConfig)
        .where(RankingConfig.session_id == session_id)
        .order_by(RankingConfig.created_at.desc())
    )
    return list(result.scalars().all())