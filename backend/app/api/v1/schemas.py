from pydantic import BaseModel, EmailStr, ConfigDict, Field
from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- 1. AUTHENTIFICATION & UTILISATEURS ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- 2. GESTION DES SESSIONS ---
class SessionCreate(BaseModel):
    name: str = Field(..., example="Admission Ph.D. 2025")
    academic_year: str = Field(..., example="2025-2026")
    qs_year: int = Field(default=2025)

class SessionRead(SessionCreate):
    id: UUID
    status: str
    created_at: datetime
    closed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

# --- 3. CONFIGURATIONS DE CLASSEMENT (RANKING) ---
class RankingConfigRequest(BaseModel):
    name: str
    weights: Dict[str, float]
    tiebreak_field: Optional[str] = "bsc_gpa_normalised"
    is_default: bool = False

class RankingConfigRead(RankingConfigRequest):
    id: UUID
    session_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- 4. DOCUMENTS ET MÉTRIQUES DÉTAILLÉES ---
class DocumentRead(BaseModel):
    id: UUID
    applicant_id: UUID
    document_type: str  # cv | transcript
    file_type: str
    original_filename: str
    ocr_quality_score: Optional[float] = None
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MetricsRead(BaseModel):
    applicant_id: UUID
    # BSc — complet
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    bsc_gpa_raw: Optional[float] = None
    bsc_gpa_scale: Optional[float] = None
    bsc_gpa_normalised: Optional[float] = None
    # MSc — complet
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    msc_gpa_raw: Optional[float] = None
    msc_gpa_scale: Optional[float] = None
    msc_gpa_normalised: Optional[float] = None
    msc_absent: Optional[bool] = False
    # Méta extraction
    global_confidence: float = 0.0
    llm_used: bool = False
    extraction_source_detail: Optional[Dict[str, Any]] = None
    model_used: Optional[str] = None
    extracted_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class PublicationRead(BaseModel):
    id: UUID
    pub_type: str
    title: Optional[str] = None
    authors_raw: Optional[str] = None
    year: Optional[int] = None
    author_position: Optional[int] = None
    total_authors: Optional[int] = None
    first_author: bool = False
    contribution_score: float = 0.0
    scopus_pct_at_extraction: Optional[float] = None
    core_score_at_extraction: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

# --- 5. CANDIDATS (VUES DASHBOARD ET DÉTAILS) ---
class ApplicantRead(BaseModel):
    id: UUID
    application_ref: str
    full_name: str
    email: Optional[str] = None
    nationality: Optional[str] = None
    status: str
    needs_human_review: bool
    pairing_complete: bool
    last_composite_score: Optional[float] = None
    last_rank: Optional[int] = None
    # BSc — complet
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    bsc_gpa_raw: Optional[float] = None
    bsc_gpa_scale: Optional[float] = None
    bsc_gpa_normalised: Optional[float] = None
    # MSc — complet
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    msc_gpa_raw: Optional[float] = None
    msc_gpa_scale: Optional[float] = None
    msc_gpa_normalised: Optional[float] = None
    msc_absent: Optional[bool] = False
    # Méta extraction
    global_confidence: Optional[float] = 0.0
    llm_used: Optional[bool] = False
    model_used: Optional[str] = None
    pub_count: int = 0
    model_config = ConfigDict(from_attributes=True)

class ApplicantDetail(ApplicantRead):
    cv_document_id: Optional[UUID] = None
    transcript_document_id: Optional[UUID] = None
    created_at: datetime
    metrics: Optional[MetricsRead] = None
    publications: List[PublicationRead] = []
    model_config = ConfigDict(from_attributes=True)

# --- 6. RÉSULTATS ET AUDIT ---
class RankingResultRead(BaseModel):
    id: UUID
    computed_at: datetime
    scores_snapshot: List[Dict[str, Any]]
    model_config = ConfigDict(from_attributes=True)

class ManualOverrideCreate(BaseModel):
    table_name: str
    record_id: UUID
    field_name: str
    old_value: Optional[str] = None
    new_value: str
    reason: str

class AuditLogRead(BaseModel):
    id: int
    action_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    occurred_at: datetime
    model_config = ConfigDict(from_attributes=True)