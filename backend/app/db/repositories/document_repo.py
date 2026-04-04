"""
backend/app/db/repositories/document_repo.py

CRUD pour Document.
Remplace le fichier existant en s'appuyant sur models.py exact.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Document


async def create_document(
    db:                AsyncSession,
    applicant_id:      uuid.UUID,
    document_type:     str,           # "cv" | "transcript"
    file_type:         str,           # "native_pdf" | "scanned_pdf" | "docx" | "error"
    original_filename: str,
    storage_path:      str,
    file_hash:         str,
    file_size_bytes:   Optional[int]   = None,
    mime_type:         Optional[str]   = None,
    ocr_quality_score: Optional[float] = None,
    uploaded_by:       Optional[uuid.UUID] = None,
) -> Document:
    """Enregistre un document uploadé en base."""
    doc = Document(
        applicant_id=applicant_id,
        document_type=document_type,
        file_type=file_type,
        original_filename=original_filename,
        storage_path=storage_path,
        file_hash=file_hash,
        file_size_bytes=file_size_bytes,
        mime_type=mime_type,
        ocr_quality_score=ocr_quality_score,
        uploaded_by=uploaded_by,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


async def get_document(
    db:          AsyncSession,
    document_id: uuid.UUID,
) -> Optional[Document]:
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


async def get_documents_for_applicant(
    db:            AsyncSession,
    applicant_id:  uuid.UUID,
    document_type: Optional[str] = None,  # "cv" | "transcript" | None
) -> list[Document]:
    """Retourne les documents d'un candidat, filtrés par type si fourni."""
    q = select(Document).where(Document.applicant_id == applicant_id)
    if document_type:
        q = q.where(Document.document_type == document_type)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_ocr_quality(
    db:                AsyncSession,
    document_id:       uuid.UUID,
    ocr_quality_score: float,
    file_type:         str,
) -> None:
    """Met à jour le score OCR et le type détecté après analyse du fichier."""
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(ocr_quality_score=ocr_quality_score, file_type=file_type)
    )


async def document_exists_by_hash(
    db:        AsyncSession,
    file_hash: str,
) -> bool:
    """Détecte les doublons par hash SHA-256 avant insertion."""
    result = await db.execute(
        select(Document.id).where(Document.file_hash == file_hash).limit(1)
    )
    return result.scalar_one_or_none() is not None