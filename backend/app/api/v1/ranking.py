import uuid
import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, ExtractedMetrics, Publication, RankingConfig as DBRankingConfig
from backend.app.db.repositories.scoring_repo import (
    save_ranking_and_update_applicants, get_latest_ranking, list_ranking_history, log_action,
)
from backend.app.api.v1.auth import check_evaluator
from src.scoring.engine import compute_scores_batch, RankingConfig as EngineConfig
from src.scoring.normalizer import normalise_candidate
from src.scoring.ranker import rank

router = APIRouter(tags=["Ranking"])

# Verrou pour éviter les race conditions
# NOTE: this is a plain in-process set — it only protects against concurrent
# requests within a single worker process. Running the API with more than
# one worker (e.g. `uvicorn --workers N`, or multiple replicas) reopens the
# race it's meant to prevent; a real fix needs a shared lock (Redis SETNX,
# same pattern already used in src/pipeline/screening_pipeline.py).
_calculating_sessions: set = set()


@router.post("/ranking")
async def compute_ranking(
    session_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    """Calcule le classement des candidats pour une session donnée."""

    session_key = str(session_id)
    if session_key in _calculating_sessions:
        raise HTTPException(409, "Ranking calculation already in progress for this session")

    config_res = await db.execute(select(DBRankingConfig).where(DBRankingConfig.id == config_id))
    db_c = config_res.scalar_one_or_none()
    if not db_c:
        raise HTTPException(404, "Ranking config not found")

    try:
        engine_cfg = EngineConfig.from_db_weights(db_c.weights)
        engine_cfg.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ranking configuration: {e}")

    res = await db.execute(
        select(Applicant).where(
            Applicant.session_id == session_id,
            Applicant.status == 'processed'
        )
    )
    applicants = res.scalars().all()
    if not applicants:
        raise HTTPException(400, "No processed applicants found for this session")

    _calculating_sessions.add(session_key)

    try:
        engine_input = []
        for app in applicants:
            m_res = await db.execute(select(ExtractedMetrics).where(ExtractedMetrics.applicant_id == app.id))
            m = m_res.scalar_one_or_none()
            p_res = await db.execute(select(Publication).where(Publication.applicant_id == app.id))
            db_p = p_res.scalars().all()
            if m:
                engine_input.append((normalise_candidate(m, list(db_p)), str(app.id), app.full_name))

        scoring_results = compute_scores_batch(engine_input, engine_cfg)
        report = rank(scoring_results, session_id=str(session_id), tiebreak_field=db_c.tiebreak_field)

        ranked_dicts = [{
            "rank": r.rank,
            "applicant_id": r.applicant_id,
            "applicant_name": r.applicant_name,
            "final_score": r.final_score,
            "bsc_academic": r.bsc_academic,
            "msc_academic": r.msc_academic,
            "journal_score": r.journal_score,
            "conf_score": r.conf_score,
            "research_score": r.research_score,
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
        await log_action(
            db, action_type="ranking_computed", session_id=session_id,
            user_id=current_user.get("id"), entity_type="ranking_result", entity_id=ranking_log.id,
            new_state={"config_id": str(config_id), "total": report.total_candidates},
        )
        await db.commit()

        return {
            "ranking_id": str(ranking_log.id),
            "total": report.total_candidates,
            "generated_at": report.generated_at,
            "score_stats": report.score_stats,
            "needs_review_count": report.needs_review_count
        }
    except HTTPException:
        await db.rollback()
        raise
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid ranking configuration: {e}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ranking computation failed: {e}")
    finally:
        _calculating_sessions.discard(session_key)


@router.get("/ranking/latest")
async def get_latest_ranking_endpoint(
    session_id: uuid.UUID = Query(..., description="Session ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
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
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    """Génère le rapport Excel officiel pour le comité d'admission."""
    latest_res = await get_latest_ranking(db, session_id)
    if not latest_res:
        raise HTTPException(404, "No ranking found for this session")
    
    df = pd.DataFrame(latest_res.scores_snapshot)
    df = df.sort_values("rank")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Shortlist', index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Shortlist']
        
        header_format = workbook.add_format({'bold': True, 'bg_color': '#1E3A8A', 'font_color': 'white'})
        score_format = workbook.add_format({'num_format': '0.00'})
        review_format = workbook.add_format({'bg_color': '#FEE2E2'})
        
        worksheet.set_column('A:A', 8)
        worksheet.set_column('B:B', 40)
        worksheet.set_column('C:C', 12, score_format)
        worksheet.set_column('D:H', 12, score_format)
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        if 'needs_review' in df.columns:
            review_rows = df[df['needs_review'] == True].index.tolist()
            for row in review_rows:
                worksheet.set_row(row + 1, None, review_format)
        
        stats_df = pd.DataFrame([
            {"Metric": "Total Candidates", "Value": len(df)},
            {"Metric": "Needs Review", "Value": df['needs_review'].sum() if 'needs_review' in df.columns else 0},
            {"Metric": "Average Score", "Value": df['final_score'].mean() if 'final_score' in df.columns else 0},
            {"Metric": "Min Score", "Value": df['final_score'].min() if 'final_score' in df.columns else 0},
            {"Metric": "Max Score", "Value": df['final_score'].max() if 'final_score' in df.columns else 0},
            {"Metric": "Median Score", "Value": df['final_score'].median() if 'final_score' in df.columns else 0},
        ])
        stats_df.to_excel(writer, sheet_name='Statistics', index=False)
        
        if latest_res.config_id:
            config_df = pd.DataFrame([
                {"Parameter": "Session ID", "Value": str(session_id)},
                {"Parameter": "Configuration ID", "Value": str(latest_res.config_id)},
                {"Parameter": "Computed At", "Value": latest_res.computed_at.isoformat()},
            ])
            config_df.to_excel(writer, sheet_name='Configuration', index=False)
    
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
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    """Récupère l'historique des classements pour une session."""
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