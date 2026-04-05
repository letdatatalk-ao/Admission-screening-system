import uuid
import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, ExtractedMetrics, Publication, RankingConfig as DBRankingConfig
from backend.app.db.repositories.scoring_repo import save_ranking_and_update_applicants, get_latest_ranking
from src.scoring.engine import compute_scores_batch, RankingConfig as EngineConfig
from src.scoring.normalizer import normalise_candidate
from src.scoring.ranker import rank

router = APIRouter(tags=["Ranking"])


@router.post("/ranking")
async def compute_ranking(
    session_id: uuid.UUID, 
    config_id: uuid.UUID, 
    db: AsyncSession = Depends(get_db)
):
    """Calcule le classement des candidats pour une session donnée."""
    config_res = await db.execute(select(DBRankingConfig).where(DBRankingConfig.id == config_id))
    db_c = config_res.scalar_one_or_none()
    if not db_c:
        raise HTTPException(404, "Ranking config not found")
    
    engine_cfg = EngineConfig.from_db_weights(db_c.weights)

    res = await db.execute(
        select(Applicant).where(
            Applicant.session_id == session_id, 
            Applicant.status == 'processed'
        )
    )
    applicants = res.scalars().all()
    if not applicants:
        raise HTTPException(400, "No processed applicants found for this session")

    engine_input = []
    for app in applicants:
        m_res = await db.execute(select(ExtractedMetrics).where(ExtractedMetrics.applicant_id == app.id))
        m = m_res.scalar_one_or_none()
        p_res = await db.execute(select(Publication).where(Publication.applicant_id == app.id))
        db_p = p_res.scalars().all()
        if m:
            engine_input.append((normalise_candidate(m, list(db_p)), str(app.id), app.full_name))

    # Calcul des scores
    scoring_results = compute_scores_batch(engine_input, engine_cfg)
    report = rank(scoring_results, session_id=str(session_id))

    # Conversion en dict pour le repository
    ranked_dicts = [{
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
    } for r in report.ranked]

    ranking_log = await save_ranking_and_update_applicants(db, session_id, config_id, ranked_dicts)
    await db.commit()
    
    return {
        "ranking_id": str(ranking_log.id), 
        "total": report.total_candidates,
        "generated_at": report.generated_at,
        "score_stats": report.score_stats,
        "needs_review_count": report.needs_review_count
    }


@router.get("/ranking/latest")
async def get_latest_ranking_endpoint(
    session_id: uuid.UUID = Query(..., description="Session ID"),
    db: AsyncSession = Depends(get_db)
):
    """Récupère le dernier classement calculé pour une session."""
    latest_ranking = await get_latest_ranking(db, session_id)
    
    if not latest_ranking:
        raise HTTPException(404, "No ranking found for this session")
    
    return {
        "id": str(latest_ranking.id),
        "session_id": str(latest_ranking.session_id),
        "config_id": str(latest_ranking.config_id),
        "computed_at": latest_ranking.computed_at.isoformat(),
        "total_applicants": latest_ranking.total_applicants,
        "scores_snapshot": latest_ranking.scores_snapshot
    }


@router.get("/ranking/{session_id}/export")
async def export_ranking_excel(
    session_id: uuid.UUID, 
    db: AsyncSession = Depends(get_db)
):
    """Génère le rapport Excel officiel pour le comité d'admission."""
    latest_res = await get_latest_ranking(db, session_id)
    if not latest_res:
        raise HTTPException(404, "No ranking found for this session")

    # Création du DataFrame à partir du snapshot JSONB
    df = pd.DataFrame(latest_res.scores_snapshot)
    
    # Création du fichier Excel en mémoire
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Shortlist Official')
    output.seek(0)

    headers = {'Content-Disposition': f'attachment; filename="Ranking_Report_{session_id}.xlsx"'}
    return StreamingResponse(
        output, 
        headers=headers, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@router.get("/ranking/history")
async def get_ranking_history(
    session_id: uuid.UUID = Query(..., description="Session ID"),
    limit: int = Query(10, description="Number of historical runs to retrieve"),
    db: AsyncSession = Depends(get_db)
):
    """Récupère l'historique des classements pour une session."""
    from backend.app.db.repositories.scoring_repo import list_ranking_history
    
    history = await list_ranking_history(db, session_id)
    
    return {
        "session_id": str(session_id),
        "total_runs": len(history),
        "runs": [
            {
                "id": str(r.id),
                "computed_at": r.computed_at.isoformat(),
                "total_applicants": r.total_applicants,
                "config_id": str(r.config_id)
            }
            for r in history[:limit]
        ]
    }