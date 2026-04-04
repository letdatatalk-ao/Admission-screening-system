import hashlib
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from backend.app.db.database import get_db
from backend.app.api.v1.auth import check_evaluator 
from backend.app.db.repositories import (
    create_applicant, create_document, update_applicant_documents, log_action
)
from backend.app.tasks import process_documents_task

router = APIRouter(tags=["Upload"])

UPLOAD_ROOT = Path("storage/raw")

def get_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

@router.post("/upload")
async def upload_documents(
    session_id: uuid.UUID,
    cv: UploadFile = File(...),
    transcript: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(check_evaluator)
):
    # 1. Lecture des contenus
    cv_content = await cv.read()
    tr_content = await transcript.read()

    # 2. Dossier physique
    applicant_uuid = uuid.uuid4()
    folder_path = UPLOAD_ROOT / str(session_id) / str(applicant_uuid)
    folder_path.mkdir(parents=True, exist_ok=True)

    # 3. Hashes
    cv_hash = get_file_hash(cv_content)
    tr_hash = get_file_hash(tr_content)

    # 4. Écriture des fichiers
    cv_path = folder_path / f"cv_{cv.filename}"
    tr_path = folder_path / f"tr_{transcript.filename}"

    try:
        with cv_path.open("wb") as f:
            f.write(cv_content)
        with tr_path.open("wb") as f:
            f.write(tr_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur disque: {str(e)}")

    # 5. Enregistrement DB
    # On utilise le nom du fichier comme nom par défaut
    applicant = await create_applicant(
        db, 
        session_id=session_id, 
        application_ref=f"APP-{str(applicant_uuid)[:8]}",
        full_name=cv.filename
    )

    cv_doc = await create_document(
        db, applicant.id, "cv", "native_pdf", cv.filename, 
        str(cv_path), cv_hash, uploaded_by=current_user["id"]
    )

    tr_doc = await create_document(
        db, applicant.id, "transcript", "native_pdf", transcript.filename, 
        str(tr_path), tr_hash, uploaded_by=current_user["id"]
    )

    # Liaison et commit
    await update_applicant_documents(db, applicant.id, cv_doc.id, tr_doc.id)
    await db.commit()
    await db.refresh(applicant)

    # 6. Lancement Pipeline Async
    task = process_documents_task.delay(str(applicant.id))

    # 7. Audit log
    await log_action(
        db, "UPLOAD_PAIRED_DOCS", session_id=session_id, 
        entity_id=applicant.id, user_id=current_user["id"]
    )
    await db.commit()

    return {
        "applicant_id": applicant.id, 
        "task_id": task.id, 
        "status": "processing"
    }