import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from backend.app.db.database import get_db
from backend.app.db.repositories import get_document
from backend.app.api.v1.auth import check_evaluator

router = APIRouter(tags=["Files"])


@router.get("/files/{document_id}")
async def get_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator),
):
    doc = await get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.isfile(doc.storage_path):
        raise HTTPException(status_code=404, detail="Document file missing from storage")
    return FileResponse(doc.storage_path, filename=doc.original_filename)