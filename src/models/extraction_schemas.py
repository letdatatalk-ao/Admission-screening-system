from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Union
import logging
import re

logger = logging.getLogger(__name__)

# Separators an LLM sometimes uses to cram two institutions into one field
# (e.g. a candidate with two Master's degrees) despite prompt instructions
# not to. Defensive cleanup: keep only the first institution.
_MULTI_UNI_SEPARATORS = re.compile(r"\s*;\s*|\s*/\s*(?=[A-Z])")
_INSTITUTION_KEYWORDS = re.compile(
    r"\b(university|universit[ée]|institute|institut|college|coll[eè]ge|"
    r"[ée]cole|academy|acad[ée]mie)\b",
    re.IGNORECASE,
)


def _first_institution_only(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    parts = [p.strip() for p in _MULTI_UNI_SEPARATORS.split(v) if p.strip()]
    if len(parts) > 1:
        logger.warning(f"Concatenated institution names — keeping first: {v!r} -> {parts[0]!r}")
        return parts[0]
    and_parts = re.split(r"\s+and\s+", v, flags=re.IGNORECASE)
    if len(and_parts) == 2 and all(_INSTITUTION_KEYWORDS.search(p) for p in and_parts):
        kept = and_parts[0].strip()
        logger.warning(f"Concatenated institution names (and) — keeping first: {v!r} -> {kept!r}")
        return kept
    return v


class GPASchema(BaseModel):
    raw_value: Optional[float] = None
    scale: Optional[float] = 4.0

    @field_validator('raw_value')
    @classmethod
    def validate_gpa_value(cls, v):
        if v is None:
            return None
        if v > 100 or v < 0:
            return None
        return round(v, 3)

    @field_validator('scale')
    @classmethod
    def validate_scale(cls, v):
        if v is None:
            return 4.0
        valid = [4.0, 5.0, 10.0, 20.0, 100.0]
        if v > 100:
            return 4.0
        # Break ties by preferring the LARGER scale — prevents raw_value > scale
        # e.g. scale=4.5 → 5.0 (not 4.0), so a 4.5/5.0 GPA stays valid
        return min(valid, key=lambda x: (abs(x - v), -x))

    @model_validator(mode='after')
    def check_gpa_valid(self):
        """If raw_value > scale the GPA is logically invalid. Auto-correct the scale."""
        if self.raw_value is not None and self.scale is not None and self.scale > 0:
            if self.raw_value > self.scale:
                valid = [4.0, 5.0, 10.0, 20.0, 100.0]
                corrected = next((s for s in valid if s >= self.raw_value), None)
                if corrected:
                    logger.debug(
                        f"GPA scale auto-corrected: {self.raw_value}/{self.scale} "
                        f"→ {self.raw_value}/{corrected}"
                    )
                    self.scale = corrected
                else:
                    self.raw_value = None
        return self


class PublicationSchema(BaseModel):
    title: Optional[str] = None
    authors: Optional[Union[str, List[str]]] = None
    year: Optional[int] = None
    pub_type: Optional[str] = "journal"
    venue: Optional[str] = None
    doi: Optional[str] = None
    author_position: Optional[Union[int, str]] = Field(1)
    total_authors: Optional[int] = Field(1, ge=1)
    is_corresponding: bool = False
    under_review: bool = False

    @field_validator('authors', mode='before')
    @classmethod
    def coerce_authors_to_string(cls, v):
        if v is None:
            return None
        if isinstance(v, list):
            return ', '.join(str(a) for a in v)
        return str(v)

    @field_validator('year', mode='before')
    @classmethod
    def coerce_year(cls, v):
        if v is None:
            return None
        try:
            year = int(v)
            return year if 1900 <= year <= 2030 else None
        except (ValueError, TypeError):
            return None

    @field_validator('pub_type', mode='before')
    @classmethod
    def coerce_pub_type(cls, v):
        if not v:
            return "journal"
        v = str(v).lower().strip()
        if v in ("journal", "conference", "book_chapter", "preprint", "thesis"):
            return v
        if any(x in v for x in ("conf", "proceeding", "workshop", "symposium")):
            return "conference"
        if "book" in v or "chapter" in v:
            return "book_chapter"
        if "preprint" in v or "arxiv" in v:
            return "preprint"
        return "journal"

    @field_validator('author_position', mode='before')
    @classmethod
    def coerce_author_position(cls, v):
        if v is None:
            return 1
        if isinstance(v, int):
            return max(1, v)
        s = str(v).strip().lower()
        semantic = {
            'first': 1, '1st': 1, 'second': 2, '2nd': 2,
            'third': 3, '3rd': 3, 'co-author': 2, 'coauthor': 2,
            'corresponding': 1, 'last': None,
        }
        if s in semantic:
            r = semantic[s]
            return r if r is not None else 1
        try:
            return max(1, int(float(s)))
        except (ValueError, TypeError):
            return 1

    @model_validator(mode='after')
    def check_position_logic(self):
        if self.author_position and self.total_authors:
            if self.author_position > self.total_authors:
                self.author_position = self.total_authors
        return self


class ExtractedCandidate(BaseModel):
    # ── Identity ──────────────────────────────────────────────
    full_name: Optional[str] = None
    email: Optional[str] = None
    nationality: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None

    # ── Bachelor ──────────────────────────────────────────────
    bsc_uni: Optional[str] = None
    bsc_country: Optional[str] = None
    bsc_field: Optional[str] = None
    bsc_year: Optional[int] = None
    bsc_gpa: GPASchema = Field(default_factory=GPASchema)

    # ── Master ────────────────────────────────────────────────
    msc_absent: bool = False
    msc_uni: Optional[str] = None
    msc_country: Optional[str] = None
    msc_field: Optional[str] = None
    msc_year: Optional[int] = None
    msc_gpa: Optional[GPASchema] = None

    # ── PhD ───────────────────────────────────────────────────
    phd_uni: Optional[str] = None
    phd_field: Optional[str] = None
    phd_year: Optional[int] = None

    # ── Research ─────────────────────────────────────────────
    publications: List[PublicationSchema] = []
    research_interests: List[str] = []
    awards: List[str] = []

    # ── Test scores ───────────────────────────────────────────
    gre_verbal: Optional[int] = None
    gre_quant: Optional[int] = None
    gre_awa: Optional[float] = None
    ielts_score: Optional[float] = None
    toefl_score: Optional[int] = None

    # ── Professional ─────────────────────────────────────────
    work_exp_years: Optional[float] = None

    @field_validator('bsc_uni', 'msc_uni', 'phd_uni', mode='before')
    @classmethod
    def clean_concatenated_university(cls, v):
        return _first_institution_only(v) if isinstance(v, str) else v

    @field_validator('bsc_year', 'msc_year', 'phd_year', mode='before')
    @classmethod
    def validate_academic_year(cls, v):
        if v is None:
            return None
        try:
            year = int(v)
            return year if 1950 <= year <= 2030 else None
        except (TypeError, ValueError):
            return None

    @field_validator('gre_verbal', 'gre_quant', mode='before')
    @classmethod
    def validate_gre(cls, v):
        if v is None:
            return None
        try:
            s = int(v)
            return s if 130 <= s <= 170 else None
        except (TypeError, ValueError):
            return None

    @field_validator('ielts_score', mode='before')
    @classmethod
    def validate_ielts(cls, v):
        if v is None:
            return None
        try:
            s = float(v)
            return round(s, 1) if 0.0 <= s <= 9.0 else None
        except (TypeError, ValueError):
            return None

    @field_validator('toefl_score', mode='before')
    @classmethod
    def validate_toefl(cls, v):
        if v is None:
            return None
        try:
            s = int(v)
            return s if 0 <= s <= 120 else None
        except (TypeError, ValueError):
            return None

    @field_validator('work_exp_years', mode='before')
    @classmethod
    def validate_work_exp(cls, v):
        if v is None:
            return None
        try:
            s = float(v)
            return round(s, 1) if 0.0 <= s <= 50.0 else None
        except (TypeError, ValueError):
            return None

    @model_validator(mode='after')
    def infer_msc_absent(self):
        return self
