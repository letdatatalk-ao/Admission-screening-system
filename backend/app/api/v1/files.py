import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from backend.app.db.database import get_db
from backend.app.db.repositories import get_document
from backend.app.api.v1.auth import SECRET_KEY, ALGORITHM

router = APIRouter(tags=["Files"])


async def check_evaluator_header_or_query(
    request: Request,
    token: Optional[str] = Query(default=None, description="JWT, for <iframe>/<img> embeds that can't send an Authorization header"),
):
    """
    Same role check as check_evaluator, but also accepts the JWT as a
    ?token= query parameter. The Review page embeds this endpoint directly
    in an <iframe src="..."> to show the CV/transcript — a browser never
    attaches a custom Authorization header to a plain iframe/img request,
    so a header-only auth dependency 401s on every embedded preview. A
    ?token= query string is the standard fallback for authenticated embeds
    (same pattern used by e.g. signed media URLs). Reads the header
    manually (rather than depending on the shared oauth2_scheme) because
    that dependency auto-raises 401 on a missing header before a fallback
    to the query param would ever run.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role = payload.get("role")
        if role not in ("admin", "evaluator"):
            raise HTTPException(status_code=403, detail="Evaluator access required")
        return {"email": payload.get("sub"), "role": role, "id": payload.get("id")}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("/files/{document_id}")
async def get_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(check_evaluator_header_or_query),
):
    doc = await get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.isfile(doc.storage_path):
        raise HTTPException(status_code=404, detail="Document file missing from storage")
    # content_disposition_type="inline" — this endpoint is embedded directly in
    # an <iframe src="..."> on the Review page (see docstring above). FileResponse
    # defaults to "attachment", which makes the browser treat the response as a
    # download and abort the iframe navigation instead of rendering it, leaving
    # the document viewer blank.
    return FileResponse(
        doc.storage_path,
        filename=doc.original_filename,
        content_disposition_type="inline",
    )