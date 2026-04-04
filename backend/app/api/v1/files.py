from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from backend.app.db.database import get_db
from backend.app.db.repositories import get_document

router = APIRouter(tags=["Files"])


@router.get("/files/{document_id}")
async def get_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = await get_document(db, document_id)
    return FileResponse(doc.storage_path)