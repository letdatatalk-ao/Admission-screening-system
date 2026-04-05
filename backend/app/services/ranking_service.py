"""
backend/app/services/ranking_service.py

Service métier pour le calcul du ranking.
"""

from __future__ import annotations

import uuid
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.db.models import Applicant, ExtractedMetrics, Publication, RankingConfig as DBRankingConfig
from backend.app.db.repositories.scoring_repo import save_ranking_and_update_applicants, get_latest_ranking
from src.scoring.normalizer import normalise_candidate
from src.scoring.engine import compute_scores_batch, RankingConfig as EngineConfig
from src.scoring.ranker import rank, RankingReport


async def get_applicants_with_metrics(
    db: AsyncSession,
    session_id: uuid.UUID,
    status: str = "processed"
) -> List[Tuple]:
    """
    Récupère tous les candidats traités d'une session avec leurs métriques et publications.
    """
    result = await db.execute(
        select(Applicant).where(
            Applicant.session_id == session_id,
            Applicant.status == status
        )
    )
    applicants = result.scalars().all()
    
    engine_input = []
    for app in applicants:
        # Récupérer les métriques
        metrics_result = await db.execute(
            select(ExtractedMetrics).where(ExtractedMetrics.applicant_id == app.id)
        )
        metrics = metrics_result.scalar_one_or_none()
        
        # Récupérer les publications
        pubs_result = await db.execute(
            select(Publication).where(Publication.applicant_id == app.id)
        )
        publications = pubs_result.scalars().all()
        
        if metrics:
            normalised = normalise_candidate(metrics, list(publications))
            engine_input.append((normalised, str(app.id), app.full_name))
    
    return engine_input


async def compute_ranking(
    db: AsyncSession,
    session_id: uuid.UUID,
    config_id: uuid.UUID,
    computed_by: Optional[uuid.UUID] = None
) -> RankingReport:
    """
    Calcule le classement complet pour une session.
    """
    # 1. Récupérer la configuration
    config_result = await db.execute(
        select(DBRankingConfig).where(DBRankingConfig.id == config_id)
    )
    db_config = config_result.scalar_one_or_none()
    
    if not db_config:
        raise ValueError(f"Ranking config {config_id} not found")
    
    # 2. Convertir en EngineConfig
    engine_config = EngineConfig.from_db_weights(db_config.weights)
    
    # 3. Récupérer les candidats avec leurs métriques
    candidates_data = await get_applicants_with_metrics(db, session_id)
    
    if not candidates_data:
        raise ValueError(f"No processed applicants found for session {session_id}")
    
    # 4. Calculer les scores
    scoring_results = compute_scores_batch(candidates_data, engine_config)
    
    # 5. Générer le classement
    report = rank(scoring_results, session_id=str(session_id))
    
    # 6. Persister les résultats
    ranked_dicts = [
        {
            "rank": r.rank,
            "applicant_id": r.applicant_id,
            "applicant_name": r.applicant_name,
            "final_score": r.final_score,
            "bsc_academic": r.bsc_academic,
            "msc_academic": r.msc_academic,
            "journal_score": r.journal_score,
            "conf_score": r.conf_score,
            "needs_review": r.needs_review,
            "missing_fields": r.missing_fields,
            "tiebreak_used": r.tiebreak_used,
            "justification": r.justification,
            "bsc_gpa_norm": r.bsc_gpa_norm,
            "msc_gpa_norm": r.msc_gpa_norm,
            "bsc_qs_score": r.bsc_qs_score,
            "msc_qs_score": r.msc_qs_score
        }
        for r in report.ranked
    ]
    
    await save_ranking_and_update_applicants(
        db=db,
        session_id=session_id,
        config_id=config_id,
        ranked_results=ranked_dicts,
        computed_by=computed_by
    )
    
    return report


async def get_session_ranking(
    db: AsyncSession,
    session_id: uuid.UUID
) -> Optional[dict]:
    """
    Récupère le dernier classement calculé pour une session.
    """
    ranking = await get_latest_ranking(db, session_id)
    if not ranking:
        return None
    
    return {
        "id": str(ranking.id),
        "session_id": str(ranking.session_id),
        "config_id": str(ranking.config_id),
        "computed_at": ranking.computed_at.isoformat(),
        "total_applicants": ranking.total_applicants,
        "scores_snapshot": ranking.scores_snapshot
    }