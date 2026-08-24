from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.database import get_db
from backend.app.db.repositories import create_session, list_sessions, create_ranking_config
from backend.app.api.v1.auth import check_evaluator
from .schemas import SessionCreate, RankingConfigRequest
import uuid

router = APIRouter(tags=["Sessions"])

@router.post("/sessions")
async def start_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    # 1. Création de l'objet via le repository
    session = await create_session(db, data.name, data.academic_year, data.qs_year)

    # 2. SAUVEGARDE RÉELLE DANS LA BASE (Le Commit)
    await db.commit()

    # 3. Rafraîchissement pour récupérer l'ID et les timestamps générés
    await db.refresh(session)

    return session

@router.get("/sessions")
async def get_all_sessions(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    return await list_sessions(db)

@router.post("/sessions/{session_id}/configs")
async def add_config(
    session_id: uuid.UUID,
    data: RankingConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    # Weight-sum validation lives in RankingConfigRequest itself (schemas.py) —
    # a bad config used to only get caught later, as an uncaught 500, when
    # POST /ranking ran RankingConfig.validate() inside the scoring engine.
    # 1. Création de la configuration
    config = await create_ranking_config(db, session_id, data.name, data.weights, tiebreak_field=data.tiebreak_field)

    # 2. SAUVEGARDE RÉELLE DANS LA BASE
    await db.commit()

    # 3. Rafraîchissement
    await db.refresh(config)

    return config