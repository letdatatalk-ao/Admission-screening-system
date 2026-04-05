# src/models/extraction_schemas.py

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class GPASchema(BaseModel):
    raw_value: Optional[float] = None
    scale: Optional[float] = 4.0

    @field_validator('raw_value')
    @classmethod
    def validate_gpa_value(cls, v):
        if v is None:
            return None
        if v > 100:
            return None
        if v < 0:
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
        closest = min(valid, key=lambda x: abs(x - v))
        return closest


class PublicationSchema(BaseModel):
    title: Optional[str] = None
    authors: Optional[Union[str, List[str]]] = None
    year: Optional[int] = None  # ← CORRIGÉ : plus de validation stricte
    venue: Optional[str] = None
    author_position: Optional[Union[int, str]] = Field(1)
    total_authors: Optional[int] = Field(1, ge=1)

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
        """Convertit l'année en entier, retourne None si non valide."""
        if v is None:
            return None
        try:
            year = int(v)
            # Année plausible entre 1900 et 2030
            if 1900 <= year <= 2030:
                return year
            return None
        except (ValueError, TypeError):
            logger.debug(f"Invalid year value: {v}, setting to None")
            return None

    @field_validator('author_position', mode='before')
    @classmethod
    def coerce_author_position(cls, v):
        if v is None:
            return 1
        if isinstance(v, int):
            return v
        s = str(v).strip().lower()
        semantic_map = {
            'first': 1, '1st': 1, 'second': 2, '2nd': 2,
            'third': 3, '3rd': 3, 'last': None,
            'co-author': 2, 'co_author': 2, 'coauthor': 2,
            'corresponding': 1,
        }
        if s in semantic_map:
            result = semantic_map[s]
            return result if result is not None else 1
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 1

    @model_validator(mode='after')
    def check_position_logic(self):
        if self.author_position and self.total_authors:
            if self.author_position > self.total_authors:
                self.author_position = self.total_authors
        return self


class ExtractedCandidate(BaseModel):
    bsc_uni: Optional[str] = None
    bsc_gpa: GPASchema = Field(default_factory=GPASchema)

    msc_absent: bool = False
    msc_uni: Optional[str] = None
    msc_gpa: Optional[GPASchema] = None

    publications: List[PublicationSchema] = []

    full_name: Optional[str] = None
    email: Optional[str] = None
    nationality: Optional[str] = None

    @model_validator(mode='after')
    def infer_msc_absent(self):
        if not self.msc_uni and not self.msc_gpa:
            self.msc_absent = True
        return self