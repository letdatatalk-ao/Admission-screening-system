from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
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
    tiebreak_field: Optional[str] = "msc_academic"
    is_default: bool = False

    @field_validator("weights")
    @classmethod
    def validate_weights_sum_to_100(cls, v):
        total = sum(float(x) for x in v.values())
        if abs(total - 100.0) > 0.5:
            raise ValueError(f"weights must sum to 100, got {total}")
        return v

class RankingConfigRead(RankingConfigRequest):
    id: UUID
    session_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- 4. DOCUMENTS ET MÉTRIQUES DÉTAILLÉES ---
class DocumentRead(BaseModel):
    id: UUID
    applicant_id: UUID
    document_type: str
    file_type: str
    original_filename: str
    ocr_quality_score: Optional[float] = None
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MetricsRead(BaseModel):
    applicant_id: Optional[UUID] = None
    # BSc
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    bsc_gpa_raw: Optional[float] = None
    bsc_gpa_scale: Optional[float] = None
    bsc_gpa_normalised: Optional[float] = None
    bsc_field: Optional[str] = None
    bsc_country: Optional[str] = None
    bsc_year: Optional[int] = None
    # MSc
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    msc_gpa_raw: Optional[float] = None
    msc_gpa_scale: Optional[float] = None
    msc_gpa_normalised: Optional[float] = None
    msc_absent: Optional[bool] = False
    msc_field: Optional[str] = None
    msc_country: Optional[str] = None
    msc_year: Optional[int] = None
    # PhD
    phd_uni_name: Optional[str] = None
    phd_field: Optional[str] = None
    phd_year: Optional[int] = None
    phd_qs_rank: Optional[int] = None
    # Test scores
    gre_verbal: Optional[int] = None
    gre_quant: Optional[int] = None
    gre_awa: Optional[float] = None
    ielts_score: Optional[float] = None
    toefl_score: Optional[int] = None
    # Professional
    work_exp_years: Optional[float] = None
    # Research
    research_interests: Optional[List[str]] = None
    awards: Optional[List[str]] = None
    # Meta
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
    doi: Optional[str] = None
    venue_name: Optional[str] = None
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
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    bsc_gpa_raw: Optional[float] = None
    bsc_gpa_scale: Optional[float] = None
    bsc_gpa_normalised: Optional[float] = None
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    msc_gpa_raw: Optional[float] = None
    msc_gpa_scale: Optional[float] = None
    msc_gpa_normalised: Optional[float] = None
    msc_absent: Optional[bool] = False
    global_confidence: Optional[float] = 0.0
    llm_used: Optional[bool] = False
    model_used: Optional[str] = None
    pub_count: int = 0
    retry_count: Optional[int] = 0
    last_error: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ApplicantDetail(BaseModel):
    id: str
    application_ref: Optional[str] = None
    full_name: str
    email: Optional[str] = None
    nationality: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    status: str
    needs_human_review: bool
    pairing_complete: Optional[bool] = False
    last_composite_score: Optional[float] = None
    last_rank: Optional[int] = None
    # BSc
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    bsc_gpa_raw: Optional[float] = None
    bsc_gpa_scale: Optional[float] = None
    bsc_gpa_normalised: Optional[float] = None
    # MSc
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    msc_gpa_raw: Optional[float] = None
    msc_gpa_scale: Optional[float] = None
    msc_gpa_normalised: Optional[float] = None
    msc_absent: Optional[bool] = False
    # Meta
    global_confidence: Optional[float] = 0.0
    llm_used: Optional[bool] = False
    model_used: Optional[str] = None
    pub_count: Optional[int] = 0
    cv_document_id: Optional[str] = None
    transcript_document_id: Optional[str] = None
    created_at: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    publications: List[Dict[str, Any]] = []
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


# --- 7. VALIDATED PATCH / CREATE SCHEMAS ---

_VALID_PUB_TYPES = {"journal", "conference", "book_chapter", "preprint", "thesis"}


class MetricsPatchRequest(BaseModel):
    # Identity fields
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    nationality: Optional[str] = None
    needs_human_review: Optional[bool] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    # Audit — required by the Review UI, was previously silently dropped
    # because this field didn't exist on the schema.
    review_reason: Optional[str] = None
    # BSc
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = Field(default=None, ge=0, le=2000)
    bsc_gpa_raw: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    bsc_gpa_scale: Optional[float] = Field(default=None, gt=0.0, le=100.0)
    bsc_gpa_normalised: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    bsc_field: Optional[str] = None
    bsc_country: Optional[str] = None
    bsc_year: Optional[int] = Field(default=None, ge=1950, le=2030)
    # MSc
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = Field(default=None, ge=0, le=2000)
    msc_gpa_raw: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    msc_gpa_scale: Optional[float] = Field(default=None, gt=0.0, le=100.0)
    msc_gpa_normalised: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    msc_absent: Optional[bool] = None
    msc_field: Optional[str] = None
    msc_country: Optional[str] = None
    msc_year: Optional[int] = Field(default=None, ge=1950, le=2030)
    # PhD
    phd_uni_name: Optional[str] = None
    phd_field: Optional[str] = None
    phd_year: Optional[int] = Field(default=None, ge=1950, le=2030)
    phd_qs_rank: Optional[int] = Field(default=None, ge=0, le=2000)
    # Test scores
    gre_verbal: Optional[int] = Field(default=None, ge=130, le=170)
    gre_quant: Optional[int] = Field(default=None, ge=130, le=170)
    gre_awa: Optional[float] = Field(default=None, ge=0.0, le=6.0)
    ielts_score: Optional[float] = Field(default=None, ge=0.0, le=9.0)
    toefl_score: Optional[int] = Field(default=None, ge=0, le=120)
    # Professional
    work_exp_years: Optional[float] = Field(default=None, ge=0.0, le=50.0)
    # Research
    research_interests: Optional[List[str]] = None
    awards: Optional[List[str]] = None
    global_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class PublicationUpdateRequest(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1900, le=2030)
    pub_type: Optional[str] = None
    authors_raw: Optional[str] = None
    author_position: Optional[int] = Field(default=None, ge=1)
    total_authors: Optional[int] = Field(default=None, ge=1)
    contribution_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    doi: Optional[str] = None
    venue: Optional[str] = None

    @field_validator("pub_type")
    @classmethod
    def validate_pub_type(cls, v):
        if v is not None and v not in _VALID_PUB_TYPES:
            raise ValueError(f"pub_type must be one of {_VALID_PUB_TYPES}")
        return v


class PublicationCreateRequest(BaseModel):
    applicant_id: UUID
    title: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1900, le=2030)
    pub_type: str = Field(default="journal")
    authors_raw: Optional[str] = None
    author_position: Optional[int] = Field(default=None, ge=1)
    total_authors: Optional[int] = Field(default=None, ge=1)
    contribution_score: float = Field(default=0.5, ge=0.0, le=1.0)
    doi: Optional[str] = None
    venue: Optional[str] = None

    @field_validator("pub_type")
    @classmethod
    def validate_pub_type(cls, v):
        if v not in _VALID_PUB_TYPES:
            raise ValueError(f"pub_type must be one of {_VALID_PUB_TYPES}")
        return v
