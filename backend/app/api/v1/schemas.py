from pydantic import BaseModel, EmailStr, ConfigDict, Field
from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- AUTH & USER ---
class Token(BaseModel):
    access_token: str
    token_type: str

class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

# --- SESSION ---
class SessionCreate(BaseModel):
    name: str
    academic_year: str
    qs_year: int

class SessionRead(SessionCreate):
    id: UUID
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- RANKING ---
class RankingConfigRequest(BaseModel): 
    name: str
    weights: Dict[str, float]
    tiebreak_field: Optional[str] = "bsc_gpa_normalised"

# --- METRICS ---
class MetricsRead(BaseModel):
    applicant_id: UUID
    bsc_uni_name: Optional[str] = None
    bsc_gpa_normalised: Optional[float] = None
    msc_uni_name: Optional[str] = None
    msc_gpa_normalised: Optional[float] = None
    global_confidence: Optional[float] = 0.0
    model_config = ConfigDict(from_attributes=True)

# --- APPLICANT (VUE DASHBOARD) ---
class ApplicantRead(BaseModel):
    id: UUID
    application_ref: str
    full_name: str
    email: Optional[str] = None
    nationality: Optional[str] = None
    status: str
    needs_human_review: bool
    last_composite_score: Optional[float] = None
    last_rank: Optional[int] = None
    
    # Champs joints (Metrics)
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    bsc_gpa_normalised: Optional[float] = None
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    msc_gpa_normalised: Optional[float] = None
    msc_absent: Optional[bool] = False
    global_confidence: Optional[float] = 0.0
    
    # Champ calculé (Count)
    pub_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class ApplicantDetail(ApplicantRead):
    cv_document_id: Optional[UUID] = None
    transcript_document_id: Optional[UUID] = None
    metrics: Optional[MetricsRead] = None
    publications: List[Any] = []
    model_config = ConfigDict(from_attributes=True)