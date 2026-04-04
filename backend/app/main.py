from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- SYNTAXE ROBUSTE (Obligatoire avec des __init__.py vides) ---
from backend.app.api.v1.upload import router as upload_router
from backend.app.api.v1.applicants import router as applicants_router
from backend.app.api.v1.ranking import router as ranking_router
from backend.app.api.v1.files import router as files_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.sessions import router as sessions_router
from backend.app.api.v1.auth import router as auth_router

app = FastAPI(
    title="PG Screening System API",
    version="1.0.0"
)

# CORS (Streamlit frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INCLUSION DES ROUTERS ---
app.include_router(upload_router, prefix="/api/v1")
app.include_router(applicants_router, prefix="/api/v1")
app.include_router(ranking_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth")