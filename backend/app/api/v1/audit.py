from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from backend.app.db.database import get_db
from backend.app.db.repositories import get_audit_trail
from backend.app.api.v1.auth import check_evaluator

router = APIRouter(tags=["Audit"])

@router.get("/audit")
async def audit(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    # Récupère les 100 dernières actions pour la session
    return await get_audit_trail(db, session_id=session_id, limit=100)