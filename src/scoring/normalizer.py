from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

def to_float(val, default: Optional[float] = None) -> Optional[float]:
    """
    Convertit Decimal, None, str → float Python.
    
    FIX: Si default=None, retourne None pour les valeurs manquantes (au lieu de 0.0)
    """
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
    Utilisé par le pipeline pour transformer les données brutes LLM.
    
    FIX: Retourne None si raw ou scale est None (au lieu de 0.0)
    """
    if raw is None or scale is None:
        return None
    
    r = to_float(raw)
    s = to_float(scale, 4.0)
    
    if r is None or s is None or s <= 0:
        return None
    
    return round((r / s) * 4.0, 3)


def norm_academic_from_db(gpa_raw, gpa_scale, qs_rank) -> NormAcademic:
    """
    Normalise les données académiques depuis la base de données.
    """
    raw = to_float(gpa_raw)
    scale = to_float(gpa_scale, 4.0)
    rank = to_float(qs_rank)
    
    # Calcul GPA normalisé (0-1)
    gpa_norm = 0.0
    needs_review = False
    missing = (raw is None)
    
    if raw is not None and scale is not None and scale > 0:
        gpa_norm = round((raw / scale), 4)
        # Si GPA normalisé > 1.0, c'est suspect (ex: GPA sur 20 converti en 4 sans ajustement)
        needs_review = (gpa_norm > 1.01)
        gpa_norm = min(gpa_norm, 1.0)  # Cap à 1.0
    
    n_gpa = NormGPA(gpa_score=gpa_norm, missing=missing, needs_review=needs_review)
    
    # Calcul score QS (0-100)
    qs_score = 15.0  # Valeur par défaut pour université non classée
    if rank is not None and rank > 0:
        # Formule: rank 1 → 100, rank 100 → 91, rank 1000 → 10
        qs_score = round(max(10.0, 100.0 - (rank - 1.0) * 0.09), 2)
    
    # Score académique composite (60% GPA, 40% QS)
    academic_score = round(n_gpa.gpa_score * 60.0 + qs_score * 0.40, 3)
    
    return NormAcademic(gpa=n_gpa, qs_score=qs_score, academic_score=academic_score)


def normalise_candidate(m, db_pubs: list) -> NormCandidate:
    """
    Normalise un candidat complet avec ses publications.
    """
    bsc = norm_academic_from_db(m.bsc_gpa_raw, m.bsc_gpa_scale, m.bsc_qs_rank)
    msc = norm_academic_from_db(m.msc_gpa_raw, m.msc_gpa_scale, m.msc_qs_rank)
    
    # Calcul des scores de publications
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
            j_tot += contrib * scopus
        elif p.pub_type == "conference":
            core = to_float(p.core_score_at_extraction, 0.0)
            if core is None:
                core = 0.0
            c_tot += contrib * (core / 10.0)  # Normalise core score (0-10) → (0-1)
    
    # Normalisation des scores (max 100)
    j_score = round(min(j_tot * 100, 100), 2) if j_tot > 0 else 0.0
    c_score = round(min(c_tot * 100, 100), 2) if c_tot > 0 else 0.0
    
    # Champs manquants
    missing = []
    if bsc.gpa.missing:
        missing.append("bsc_gpa")
    if msc.gpa.missing and not msc.missing:  # Si MSc présent mais GPA manquant
        missing.append("msc_gpa")
    
    needs_review = bsc.gpa.needs_review or msc.gpa.needs_review or len(missing) > 0
    
    return NormCandidate(
        bsc=bsc,
        msc=msc,
        journals=NormPublication(normalised_score=j_score, count=len([p for p in db_pubs if p.pub_type == "journal"])),
        conferences=NormPublication(normalised_score=c_score, count=len([p for p in db_pubs if p.pub_type == "conference"])),
        needs_review=needs_review,
        missing_fields=missing
    )