from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

def to_float(val, default: float = 0.0) -> float:
    """Convertit Decimal, None, str → float Python."""
    if val is None: return default
    try: return float(val)
    except (TypeError, ValueError): return default

to_f = to_float 

@dataclass
class NormGPA:
    gpa_score: float; missing: bool; needs_review: bool

@dataclass
class NormAcademic:
    gpa: NormGPA; qs_score: float; academic_score: float

@dataclass
class NormPublication:
    normalised_score: float; count: int

@dataclass
class NormCandidate:
    bsc: NormAcademic; msc: NormAcademic; journals: NormPublication; conferences: NormPublication
    needs_review: bool; missing_fields: list[str] = field(default_factory=list)

def normalise_gpa_to_4(raw: float, scale: float) -> float:
    """Utilisé par le pipeline pour transformer les données brutes LLM."""
    r, s = to_float(raw), to_float(scale, 4.0)
    return round((r / s) * 4.0, 3) if s > 0 else 0.0

def norm_academic_from_db(gpa_raw, gpa_scale, qs_rank) -> NormAcademic:
    raw, scale, rank = to_float(gpa_raw), to_float(gpa_scale, 4.0), to_float(qs_rank)
    gpa_norm = round((raw / scale), 4) if scale > 0 else 0.0
    n_gpa = NormGPA(gpa_score=min(gpa_norm, 1.0), missing=(gpa_raw is None), needs_review=(gpa_norm > 1.01))
    qs_score = round(max(10.0, 100.0 - (rank - 1.0) * 0.09), 2) if rank > 0 else 15.0
    academic = round(n_gpa.gpa_score * 60.0 + qs_score * 0.40, 3)
    return NormAcademic(gpa=n_gpa, qs_score=qs_score, academic_score=academic)

def normalise_candidate(m, db_pubs: list) -> NormCandidate:
    bsc = norm_academic_from_db(m.bsc_gpa_raw, m.bsc_gpa_scale, m.bsc_qs_rank)
    msc = norm_academic_from_db(m.msc_gpa_raw, m.msc_gpa_scale, m.msc_qs_rank)
    
    j_tot = sum(to_float(p.contribution_score) * to_float(p.scopus_pct_at_extraction) for p in db_pubs if p.pub_type == "journal")
    c_tot = sum(to_float(p.contribution_score) * (to_float(p.core_score_at_extraction or 0)/10.0) for p in db_pubs if p.pub_type == "conference")
    
    missing = ["bsc_gpa"] if bsc.gpa.missing else []
    return NormCandidate(bsc, msc, NormPublication(round(min(j_tot*100, 100), 2), len(db_pubs)), 
                         NormPublication(round(min(c_tot*100, 100), 2), len(db_pubs)), 
                         bsc.gpa.needs_review or msc.gpa.needs_review or bool(missing), missing)