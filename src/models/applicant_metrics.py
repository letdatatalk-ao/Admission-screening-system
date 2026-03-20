from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class PublicationMetric:
    title: Optional[str] = None
    authors_raw: Optional[str] = None
    author_position: Optional[int] = None
    total_authors: Optional[int] = None
    first_author: Optional[bool] = None
    contribution_score: Optional[float] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    journal_name: Optional[str] = None
    scopus_pct: Optional[float] = None
    conference_name: Optional[str] = None
    conference_acronym: Optional[str] = None
    core_ranking: Optional[str] = None
    core_score: Optional[int] = None
    pub_type: str = "journal"
    confidence: float = 0.0

@dataclass
class ApplicantMetrics:
    applicant_id: Optional[str] = None
    bsc_uni_name: Optional[str] = None
    bsc_qs_rank: Optional[int] = None
    msc_uni_name: Optional[str] = None
    msc_qs_rank: Optional[int] = None
    bsc_gpa_raw: Optional[float] = None
    bsc_gpa_scale: Optional[float] = None
    bsc_gpa_normalised: Optional[float] = None
    bsc_gpa_source: Optional[str] = None
    msc_gpa_raw: Optional[float] = None
    msc_gpa_scale: Optional[float] = None
    msc_gpa_normalised: Optional[float] = None
    msc_gpa_source: Optional[str] = None
    msc_absent: bool = False
    publications: List[PublicationMetric] = field(default_factory=list)
    global_confidence: float = 0.0
    llm_used: bool = False
    needs_human_review: bool = False