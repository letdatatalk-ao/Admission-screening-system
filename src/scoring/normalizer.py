from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

def to_float(val, default: Optional[float] = None) -> Optional[float]:
    """Convertit Decimal, None, str → float Python."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

to_f = to_float


@dataclass
class NormGPA:
    gpa_score: float
    missing: bool
    needs_review: bool


@dataclass
class NormAcademic:
    gpa: NormGPA
    qs_score: float
    academic_score: float
    missing: bool = False  


@dataclass
class NormPublication:
    normalised_score: float
    count: int


@dataclass
class NormCandidate:
    bsc: NormAcademic
    msc: NormAcademic
    journals: NormPublication
    conferences: NormPublication
    needs_review: bool
    missing_fields: list[str] = field(default_factory=list)


def normalise_gpa_to_4(raw: Optional[float], scale: Optional[float]) -> Optional[float]:
    """
    Transforme les données brutes LLM en GPA normalisé sur 4.0.
    
    FIX: Plafonne la valeur à 4.0 pour éviter les erreurs PostgreSQL
    """
    if raw is None or scale is None:
        return None
    r = to_float(raw)
    s = to_float(scale, 4.0)
    if r is None or s is None or s <= 0:
        return None
    
    # Calcul du GPA normalisé
    gpa_normalised = (r / s) * 4.0
    
    # FIX: Plafonner à 4.0 (évite les valeurs > 4.0 comme 8.833)
    gpa_normalised = min(gpa_normalised, 4.0)
    
    # FIX: Arrondir à 3 décimales pour correspondre à NUMERIC(4,3)
    return round(gpa_normalised, 3)


# Constantes pour la normalisation QS
QS_MAX_RANK = 1500
QS_DEFAULT_SCORE = 5.0


def normalise_qs_score(rank: Optional[float]) -> float:
    """Convertit un rang QS en score normalisé (0-100)."""
    if rank is None or rank <= 0:
        return QS_DEFAULT_SCORE
    score = max(0.0, 100.0 - (rank - 1.0) * (100.0 / QS_MAX_RANK))
    return round(score, 2)


def norm_academic_from_db(gpa_raw, gpa_scale, qs_rank) -> NormAcademic:
    """
    Normalise les données académiques depuis la base de données.
    
    FIX: La valeur GPA normalisée est maintenant correctement plafonnée
    """
    raw = to_float(gpa_raw)
    scale = to_float(gpa_scale, 4.0)
    rank = to_float(qs_rank)
    
    gpa_norm = 0.0
    needs_review = False
    missing = (raw is None)
    
    if raw is not None and scale is not None and scale > 0:
        # Calcul du GPA normalisé sur 4.0
        gpa_calc = (raw / scale) * 4.0
        
        # FIX: Plafonner à 4.0 (évite les valeurs comme 8.833)
        gpa_calc = min(gpa_calc, 4.0)
        
        # Normaliser sur 0-1 pour le scoring
        gpa_norm = round(gpa_calc / 4.0, 4)
        
        # Vérifier si la valeur est suspecte (GPA > 4.0 avant plafonnement)
        raw_gpa_calc = (raw / scale) * 4.0
        needs_review = (raw_gpa_calc > 4.1)
    
    n_gpa = NormGPA(gpa_score=gpa_norm, missing=missing, needs_review=needs_review)
    qs_score = normalise_qs_score(rank)
    qs_normalised = qs_score / 100.0
    academic_score = round(n_gpa.gpa_score * 60.0 + qs_normalised * 40.0, 3)
    
    return NormAcademic(
        gpa=n_gpa, 
        qs_score=qs_score, 
        academic_score=academic_score,
        missing=missing
    )


def normalise_candidate(m, db_pubs: list) -> NormCandidate:
    """Normalise un candidat complet avec ses publications."""
    bsc = norm_academic_from_db(m.bsc_gpa_raw, m.bsc_gpa_scale, m.bsc_qs_rank)
    msc = norm_academic_from_db(m.msc_gpa_raw, m.msc_gpa_scale, m.msc_qs_rank)
    
    j_tot = 0.0
    c_tot = 0.0
    
    for p in db_pubs:
        contrib = to_float(p.contribution_score, 1.0)
        if contrib is None:
            contrib = 1.0
        
        if p.pub_type == "journal":
            scopus = to_float(p.scopus_pct_at_extraction, 0.0)
            if scopus is None:
                scopus = 0.0
            j_tot += contrib * (scopus / 100.0)
        elif p.pub_type == "conference":
            core = to_float(p.core_score_at_extraction, 0.0)
            if core is None:
                core = 0.0
            c_tot += contrib * (core / 10.0)
    
    journal_count = len([p for p in db_pubs if p.pub_type == "journal"])
    conference_count = len([p for p in db_pubs if p.pub_type == "conference"])
    
    if journal_count > 0:
        j_score = round(min(j_tot / journal_count * 100, 100), 2)
    else:
        j_score = 0.0
    
    if conference_count > 0:
        c_score = round(min(c_tot / conference_count * 100, 100), 2)
    else:
        c_score = 0.0
    
    missing = []
    if bsc.gpa.missing:
        missing.append("bsc_gpa")
    if msc.gpa.missing and not msc.missing:
        missing.append("msc_gpa")
    
    needs_review = bsc.gpa.needs_review or msc.gpa.needs_review or len(missing) > 0
    
    return NormCandidate(
        bsc=bsc,
        msc=msc,
        journals=NormPublication(normalised_score=j_score, count=journal_count),
        conferences=NormPublication(normalised_score=c_score, count=conference_count),
        needs_review=needs_review,
        missing_fields=missing
    )