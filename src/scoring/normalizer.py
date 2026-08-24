from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

from src.scoring.config import get_scoring_config


def to_float(val, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


to_f = to_float


@dataclass
class NormGPA:
    gpa_score:    float
    missing:      bool
    needs_review: bool


@dataclass
class NormAcademic:
    gpa:            NormGPA
    qs_score:       float
    academic_score: float
    missing:        bool = False


@dataclass
class NormPublication:
    normalised_score: float
    count:            int


@dataclass
class NormResearch:
    """Research profile: PhD, work experience, raw pub count."""
    research_score: float   # 0–100
    has_phd:        bool
    work_years:     float
    pub_count:      int


@dataclass
class NormCandidate:
    bsc:           NormAcademic
    msc:           NormAcademic
    journals:      NormPublication
    conferences:   NormPublication
    research:      NormResearch
    needs_review:  bool
    missing_fields: list = field(default_factory=list)


# Countries that use an inverted grading scale (lower = better)
_INVERTED_GPA_COUNTRIES = frozenset({
    "germany", "austria", "switzerland", "luxembourg",
    "deutschland", "österreich", "allemagne",
})


def normalise_gpa_to_4(
    raw: Optional[float],
    scale: Optional[float],
    country: Optional[str] = None,
) -> Optional[float]:
    if raw is None or scale is None:
        return None
    r = to_float(raw)
    s = to_float(scale, 4.0)
    if r is None or s is None or s <= 0:
        return None

    # German/Austrian grading: 1.0 = best, 4.0/5.0 = worst passing grade.
    # Detect when: country matches AND scale is in the German range (4–6)
    # AND the raw grade is in [1, scale] (consistent with inverted scale).
    if (
        country
        and country.lower().split(",")[0].strip() in _INVERTED_GPA_COUNTRIES
        and 4.0 <= s <= 6.0
        and 1.0 <= r <= s
    ):
        # Convert: (scale - raw) / (scale - 1.0) * 4.0
        # Examples: grade 1.0/5 → 4.0/4, grade 1.5/5 → 3.5/4, grade 4.0/5 → 0.0/4
        return round(min(max((s - r) / (s - 1.0) * 4.0, 0.0), 4.0), 3)

    return round(min((r / s) * 4.0, 4.0), 3)


def normalise_qs_score(rank: Optional[float]) -> float:
    cfg = get_scoring_config()["academic"]
    qs_max     = cfg["qs_max_rank"]
    qs_default = cfg["qs_default_score"]
    if rank is None or rank <= 0:
        return qs_default
    return round(max(0.0, 100.0 - (rank - 1.0) * (100.0 / qs_max)), 2)


def norm_academic_from_db(
    gpa_raw, gpa_scale, qs_rank, country: Optional[str] = None
) -> NormAcademic:
    cfg   = get_scoring_config()["academic"]
    raw   = to_float(gpa_raw)
    scale = to_float(gpa_scale, 4.0)
    rank  = to_float(qs_rank)

    gpa_norm     = 0.0
    needs_review = False
    missing      = (raw is None)

    if raw is not None and scale and scale > 0:
        # Flag inconsistent raw/scale pairs (e.g. a manually-entered raw=4.8
        # against scale=4.0) BEFORE normalise_gpa_to_4 clamps the result —
        # the clamp caps every output at 4.0, so checking the clamped value
        # here could never be true and silently dropped this review flag.
        needs_review = raw > scale
        gpa_4        = normalise_gpa_to_4(raw, scale, country=country) or 0.0
        gpa_norm     = round(gpa_4 / 4.0, 4)

    n_gpa      = NormGPA(gpa_score=gpa_norm, missing=missing, needs_review=needs_review)
    qs_score   = normalise_qs_score(rank)
    qs_norm    = qs_score / 100.0
    gpa_w      = cfg["gpa_weight"]
    qs_w       = cfg["qs_rank_weight"]
    acad_score = round(n_gpa.gpa_score * gpa_w * 100.0 + qs_norm * qs_w * 100.0, 3)

    return NormAcademic(gpa=n_gpa, qs_score=qs_score, academic_score=acad_score, missing=missing)


def _diminishing_returns(scores: List[float]) -> float:
    """Cumulative score with configurable diminishing returns."""
    if not scores:
        return 0.0
    cfg   = get_scoring_config()["publications"]
    decay = cfg["decay_factor"]
    scale = cfg["scale"]
    weighted = sum(s * decay ** i for i, s in enumerate(sorted(scores, reverse=True)))
    return round(min(weighted * scale, 100.0), 2)


def norm_research_profile(m) -> NormResearch:
    """Research profile: PhD presence + work experience (publications excluded — no double-count)."""
    cfg        = get_scoring_config()["research_profile"]
    has_phd    = bool(getattr(m, "phd_uni_name", None))
    work_years = to_float(getattr(m, "work_exp_years", None), 0.0) or 0.0

    phd_pts  = cfg["phd_points"] if has_phd else 0.0
    work_max = cfg["work_exp_max_points"]
    work_cap = cfg["work_exp_years_for_max"]
    work_pts = min(work_years / work_cap * work_max, work_max)

    return NormResearch(
        research_score=round(phd_pts + work_pts, 2),
        has_phd=has_phd,
        work_years=work_years,
        pub_count=0,   # overridden in normalise_candidate
    )


def normalise_candidate(m, db_pubs: list) -> NormCandidate:
    bsc = norm_academic_from_db(
        m.bsc_gpa_raw, m.bsc_gpa_scale, m.bsc_qs_rank,
        country=getattr(m, "bsc_country", None),
    )
    msc = norm_academic_from_db(
        m.msc_gpa_raw, m.msc_gpa_scale, m.msc_qs_rank,
        country=getattr(m, "msc_country", None),
    )

    j_scores: List[float] = []
    c_scores: List[float] = []

    for p in db_pubs:
        # Skip publications that are not yet published — they have no verified impact
        if getattr(p, 'under_review', False):
            continue
        # NOT `to_float(...) or 1.0` — a legitimate contribution_score of 0.0
        # (e.g. a reviewer manually marking "no meaningful contribution") is
        # falsy in Python, so `or 1.0` silently replaced it with full credit.
        contrib = to_float(p.contribution_score, 1.0)
        if contrib is None:
            contrib = 1.0
        if p.pub_type == "journal":
            scopus = to_float(p.scopus_pct_at_extraction, 0.0) or 0.0
            j_scores.append(contrib * (scopus / 100.0))
        elif p.pub_type == "conference":
            core = to_float(p.core_score_at_extraction, 0.0) or 0.0
            c_scores.append(contrib * (core / 10.0))

    j_score = _diminishing_returns(j_scores)
    c_score = _diminishing_returns(c_scores)

    # Research profile — publications excluded (already in w_jour/w_conf).
    # All constants come from scoring_weights.yaml via norm_research_profile().
    res = norm_research_profile(m)
    res.pub_count = len(j_scores) + len(c_scores)  # stored for display only

    missing = []
    if bsc.gpa.missing:
        missing.append("bsc_gpa")
    if msc.gpa.missing and not getattr(m, 'msc_absent', False):
        missing.append("msc_gpa")

    needs_review = bsc.gpa.needs_review or msc.gpa.needs_review or len(missing) > 0

    return NormCandidate(
        bsc=bsc,
        msc=msc,
        journals=NormPublication(normalised_score=j_score, count=len(j_scores)),
        conferences=NormPublication(normalised_score=c_score, count=len(c_scores)),
        research=res,
        needs_review=needs_review,
        missing_fields=missing,
    )
