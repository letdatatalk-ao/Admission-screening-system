from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, Integer, Numeric, String, Text,
    DateTime, ForeignKey, BigInteger, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class EvaluationSession(Base):
    __tablename__ = "evaluation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    qs_year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)


class Applicant(Base):
    __tablename__ = "applicants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_sessions.id"), nullable=False)
    application_ref: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    cv_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    transcript_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    pairing_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    last_composite_score: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 3), nullable=True)
    last_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_ranking_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ranking_configs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    
    # ✅ NOUVEAUX CHAMPS POUR LA GESTION DES REPRISES
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    linkedin: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("idx_applicants_session", "session_id"),
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(20), nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ocr_quality_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_documents_applicant", "applicant_id"),
    )


class ExtractedMetrics(Base):
    __tablename__ = "extracted_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"),
        nullable=False, unique=True)
    cv_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    transcript_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    bsc_uni_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bsc_qs_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bsc_qs_normalised: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 3), nullable=True)
    bsc_gpa_raw: Mapped[Optional[float]] = mapped_column(
        Numeric(7, 3), nullable=True)
    bsc_gpa_scale: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 1), nullable=True)
    bsc_gpa_normalised: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 3), nullable=True)
    bsc_gpa_normalised_done: Mapped[bool] = mapped_column(Boolean, default=False)
    bsc_gpa_source: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True)
    msc_uni_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    msc_qs_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    msc_qs_normalised: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 3), nullable=True)
    msc_gpa_raw: Mapped[Optional[float]] = mapped_column(
        Numeric(7, 3), nullable=True)
    msc_gpa_scale: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 1), nullable=True)
    msc_gpa_normalised: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 3), nullable=True)
    msc_gpa_normalised_done: Mapped[bool] = mapped_column(Boolean, default=False)
    msc_gpa_source: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True)
    bsc_field:   Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bsc_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bsc_year:    Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    msc_field:   Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    msc_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    msc_year:    Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    msc_absent: Mapped[bool] = mapped_column(Boolean, default=False)
    phd_uni_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phd_field:    Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phd_year:     Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    phd_qs_rank:  Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gre_verbal:   Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gre_quant:    Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gre_awa:      Mapped[Optional[float]] = mapped_column(Numeric(3, 1), nullable=True)
    ielts_score:  Mapped[Optional[float]] = mapped_column(Numeric(3, 1), nullable=True)
    toefl_score:  Mapped[Optional[int]]   = mapped_column(Integer, nullable=True)
    work_exp_years: Mapped[Optional[float]] = mapped_column(Numeric(4, 1), nullable=True)
    research_interests: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    awards:             Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    global_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), nullable=True)
    nlp_confidence_detail: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_confidence_detail: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True)
    extraction_source_detail: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_extracted_applicant", "applicant_id"),
    )


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_type: Mapped[str] = mapped_column(
        String(20), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    acronym: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    issn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    isbn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    scopus_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True)
    scopus_quartile: Mapped[Optional[str]] = mapped_column(
        String(3), nullable=True)
    core_ranking: Mapped[Optional[str]] = mapped_column(
        String(3), nullable=True)
    core_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lookup_source: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True)
    lookup_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), nullable=True)
    qs_year_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_venues_type_name", "venue_type", "name"),
    )


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False)
    venue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("venues.id"), nullable=True)
    pub_type: Mapped[str] = mapped_column(
        String(20), nullable=False)
    position_in_cv: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_authors: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    first_author: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    contribution_score: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 3), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    isbn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    raw_citation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conference_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conference_dates: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True)
    scopus_pct_at_extraction: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True)
    core_score_at_extraction: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(3, 2), nullable=True)
    under_review: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_source: Mapped[str] = mapped_column(
        String(10), default="nlp")

    venue: Mapped[Optional["Venue"]] = relationship("Venue", foreign_keys=[venue_id])

    __table_args__ = (
        Index("idx_publications_applicant", "applicant_id"),
        Index("idx_publications_venue", "venue_id"),
    )
class RankingConfig(Base):
    __tablename__ = "ranking_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_sessions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    weights: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tiebreak_field: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class RankingResult(Base):
    __tablename__ = "ranking_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_sessions.id"), nullable=False)
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ranking_configs.id"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    computed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    total_applicants: Mapped[int] = mapped_column(Integer, nullable=False)
    scores_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("idx_ranking_session", "session_id", "computed_at"),
    )


class ManualOverride(Base):
    __tablename__ = "manual_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    overridden_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_overrides_applicant", "applicant_id"),
    )


class SupervisorProfile(Base):
    __tablename__ = "supervisor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    faculty_name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    research_areas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    max_phd_students: Mapped[int] = mapped_column(Integer, default=2)
    current_phd_count: Mapped[int] = mapped_column(Integer, default=0)
    is_accepting_students: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    matches: Mapped[list["ApplicantSupervisorMatch"]] = relationship(
        "ApplicantSupervisorMatch", back_populates="supervisor",
        cascade="all, delete-orphan")


class ApplicantSupervisorMatch(Base):
    __tablename__ = "applicant_supervisor_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False)
    supervisor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supervisor_profiles.id"), nullable=False)
    match_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    matched_keywords: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    supervisor: Mapped["SupervisorProfile"] = relationship(
        "SupervisorProfile", back_populates="matches")

    __table_args__ = (
        Index("idx_matches_applicant", "applicant_id"),
        Index("idx_matches_supervisor", "supervisor_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_sessions.id"), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True)
    old_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_audit_session_time", "session_id", "occurred_at"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
    )