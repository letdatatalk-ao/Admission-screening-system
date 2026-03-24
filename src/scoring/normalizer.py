"""
src/scoring/normalizer.py

Couche de normalisation pure.
Reçoit les dataclasses des extracteurs, produit des scores [0, 1] ou [0, 100]
prêts pour engine.py. Aucune regex, aucune I/O ici.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Reproduction minimale des dataclasses d'entrée
# En production : remplacer par
#   from src.extractors.gpa_extractor        import GPAResult
#   from src.extractors.university_extractor import UniversityResult
#   from src.extractors.publication_extractor import PublicationResult, VenueResult
# ---------------------------------------------------------------------------

@dataclass
class GPAResult:
    raw_value:      Optional[float]
    original_scale: Optional[float]
    normalised_gpa: Optional[float]
    confidence:     float
    source:         str
    raw_match:      Optional[str]
    degree_level:   str


@dataclass
class UniversityResult:
    detected_name:  Optional[str]
    qs_rank:        Optional[int]
    qs_match_name:  Optional[str]
    match_score:    float
    confidence:     float
    degree_level:   str


@dataclass
class VenueResult:
    name:         Optional[str]
    matched_name: Optional[str]
    venue_type:   str               # "journal" | "conference"
    scopus_pct:   Optional[float]   # percentile Scopus [0.0 – 1.0]
    scopus_q:     Optional[str]
    core_rank:    Optional[str]     # "A*" | "A" | "B" | "C" | "D" | None
    core_score:   Optional[int]
    match_score:  float
    confidence:   float


@dataclass
class PublicationResult:
    raw_citation:       str
    title:              Optional[str]
    year:               Optional[int]
    authors_raw:        Optional[str]
    author_position:    Optional[int]
    total_authors:      Optional[int]
    first_author:       bool
    contribution_score: float       # (n-p+1)/n déjà calculé par l'extracteur
    venue:              VenueResult
    confidence:         float
    extraction_source:  str


# ---------------------------------------------------------------------------
# Constantes métier — modifier ici uniquement
# ---------------------------------------------------------------------------

CORE_POINTS: dict[str, int] = {
    "A*": 10,
    "A":   8,
    "B":   5,
    "C":   3,
    "D":   1,
}

QS_UNRANKED_SCORE        = 15.0   # université réelle mais absente du QS
QS_SLOPE                 = 0.09   # décroissance par rang
QS_FLOOR                 = 10.0   # plancher absolu (rang > 1000)
GPA_CONFIDENCE_THRESHOLD = 0.70   # en dessous → needs_review
PUB_CAP                  = 100.0  # plafond score publications


# ---------------------------------------------------------------------------
# Dataclasses de sortie
# ---------------------------------------------------------------------------

@dataclass
class NormGPA:
    gpa_score:      float    # [0.0 – 1.0]
    missing_flag:   bool
    needs_review:   bool
    scale_inferred: bool     # True si échelle corrigée heuristiquement
    clamped:        bool     # True si valeur > 4.0 clampée
    confidence:     float
    source:         str


@dataclass
class NormAcademic:
    gpa:            NormGPA
    qs_score:       float    # [0.0 – 100.0]
    academic_score: float    # [0.0 – 100.0]
    qs_rank:        Optional[int]
    qs_unranked:    bool


@dataclass
class NormPubDetail:
    title:         Optional[str]
    author_pos:    Optional[int]
    total_authors: Optional[int]
    first_author:  bool
    contrib:       float      # (n-p+1)/n
    venue_label:   str        # "CORE A*" | "Scopus Q1 (87%)" etc.
    raw_contrib:   float      # contribution brute avant ×100


@dataclass
class NormPublication:
    normalised_score: float
    raw_score:        float
    count:            int
    details:          list[NormPubDetail] = field(default_factory=list)


@dataclass
class NormCandidate:
    bsc:            NormAcademic
    msc:            NormAcademic
    journals:       NormPublication
    conferences:    NormPublication
    needs_review:   bool
    missing_fields: list[str]


# ---------------------------------------------------------------------------
# 1. Normalisation GPA
# ---------------------------------------------------------------------------

def _infer_scale(raw: float) -> Optional[float]:
    """
    Appelé quand source == 'implicit_4' mais raw_value > 4.0.
    L'extracteur a supposé /4.0 à tort (ex: "GPA: 14.5" sur échelle /20).
    Retourne l'échelle probable ou None si non détectable.
    """
    if 4.01 <= raw <= 5.0:   return 5.0
    if 5.01 <= raw <= 20.0:  return 20.0
    if raw > 20.0:           return 100.0
    return None


def _to_scale4(raw: float, scale: float) -> float:
    """Même logique que normalise_gpa() dans gpa_extractor.py."""
    if scale == 4.0:   return round(raw, 3)
    if scale == 5.0:   return round(raw * 0.8, 3)
    if scale == 20.0:  return round(raw * 0.2, 3)
    if scale == 100.0: return round(raw * 0.04, 3)
    return round(raw / scale * 4.0, 3)


def norm_gpa(result: GPAResult) -> NormGPA:
    """
    Reçoit un GPAResult de l'extracteur et produit un NormGPA.

    5 règles appliquées dans l'ordre :
      1. GPA absent (None)
      2. Anomalie d'échelle : implicit_4 avec raw > 4.0 → ré-inférence
      3. Valeur négative (parasite OCR)
      4. Clamp si normalised_gpa > 4.0 (arrondi flottant)
      5. Conversion → [0.0, 1.0] + seuil de confiance
    """

    # Règle 1 — absent
    if result.normalised_gpa is None or result.raw_value is None:
        return NormGPA(0.0, True, True, False, False, 0.0, "not_found")

    normalised     = result.normalised_gpa
    confidence     = result.confidence
    scale_inferred = False
    source         = result.source

    # Règle 2 — anomalie d'échelle
    # Cas typique : CV tunisien avec "GPA: 14.5" (échelle /20),
    # l'extracteur retourne implicit_4 et normalised = 14.5 (faux)
    if result.source == "implicit_4" and result.raw_value > 4.0:
        inferred = _infer_scale(result.raw_value)
        if inferred:
            normalised     = _to_scale4(result.raw_value, inferred)
            confidence     = 0.55
            scale_inferred = True
            source         = f"scale_inferred/{inferred}"
        else:
            # Impossible à récupérer proprement
            return NormGPA(0.0, True, True, False, False, 0.0,
                           "anomaly_unrecoverable")

    # Règle 3 — valeur négative (OCR lit un tiret comme moins)
    if normalised < 0:
        return NormGPA(0.0, True, True, scale_inferred, False, 0.0,
                       "negative_value")

    # Règle 4 — clamp
    clamped = False
    if normalised > 4.0:
        normalised = 4.0
        clamped    = True

    # Règle 5 — conversion finale
    gpa_score    = round(normalised / 4.0, 4)
    needs_review = (confidence < GPA_CONFIDENCE_THRESHOLD) or scale_inferred

    return NormGPA(
        gpa_score=gpa_score,
        missing_flag=False,
        needs_review=needs_review,
        scale_inferred=scale_inferred,
        clamped=clamped,
        confidence=confidence,
        source=source,
    )


# ---------------------------------------------------------------------------
# 2. Normalisation rang QS (Option B)
# ---------------------------------------------------------------------------

def norm_qs(university: Optional[UniversityResult]) -> tuple[float, bool]:
    """
    Retourne (qs_score [0..100], is_unranked).

    rank 1    → 100.0
    rank 100  → 91.1
    rank 500  → 55.6
    rank 1000 → clampé à QS_FLOOR (10.0)
    non classée / None → QS_UNRANKED_SCORE (15.0)
    """
    rank = university.qs_rank if university else None
    if rank is None:
        return QS_UNRANKED_SCORE, True
    return round(max(QS_FLOOR, 100.0 - (rank - 1) * QS_SLOPE), 2), False


# ---------------------------------------------------------------------------
# 3. Score académique composite BSc / MSc
# ---------------------------------------------------------------------------

def norm_academic(
    gpa_result:  GPAResult,
    univ_result: Optional[UniversityResult],
) -> NormAcademic:
    """
    academic_score [0..100] = gpa_score * 60 + qs_score * 0.40

    gpa_score ∈ [0, 1]    → max 60 pts
    qs_score  ∈ [0, 100]  → max 40 pts
    """
    n_gpa              = norm_gpa(gpa_result)
    qs_score, unranked = norm_qs(univ_result)
    academic_score     = round(n_gpa.gpa_score * 60.0 + qs_score * 0.40, 3)

    return NormAcademic(
        gpa=n_gpa,
        qs_score=qs_score,
        academic_score=academic_score,
        qs_rank=univ_result.qs_rank if univ_result else None,
        qs_unranked=unranked,
    )


# ---------------------------------------------------------------------------
# 4. Normalisation publications
# ---------------------------------------------------------------------------

def _core_pts(rank: Optional[str]) -> int:
    if rank is None:
        return 0
    return CORE_POINTS.get(rank.strip().upper(), 0)


def _venue_label(pub: PublicationResult) -> str:
    v = pub.venue
    if v.venue_type == "journal":
        q   = f" {v.scopus_q}"        if v.scopus_q   else ""
        pct = f" ({v.scopus_pct:.0%})" if v.scopus_pct else ""
        return f"Scopus{q}{pct}"
    rank = v.core_rank or "non classée"
    return f"CORE {rank}"


def norm_publications(
    publications: list[PublicationResult],
    pub_type:     str = "conference",   # "journal" | "conference"
) -> NormPublication:
    """
    Score publications normalisé [0, PUB_CAP].

    Journaux :
        raw_contrib  = scopus_pct × contribution_score
        score_final  = min(Σ raw_contrib × 100, PUB_CAP)

    Conférences :
        raw_contrib  = (core_pts / 10) × contribution_score
        score_final  = min(Σ raw_contrib × 100, PUB_CAP)

    contribution_score = (n-p+1)/n  (avec bonus 0.85 dernier auteur senior)
    déjà calculé par publication_extractor.py — on le réutilise tel quel.

    Exemples conférences :
        A*, 1er/2  → (10/10) × 1.0   = 1.0  → 100 pts (plafonné)
        A,  2ème/3 → (8/10)  × 0.667 = 0.53 →  53 pts
        B,  1er/1  → (5/10)  × 1.0   = 0.5  →  50 pts
        non classée → 0 pts
    """
    if not publications:
        return NormPublication(0.0, 0.0, 0, [])

    raw_score = 0.0
    details   = []

    for pub in publications:
        contrib = pub.contribution_score

        if pub_type == "journal":
            pct         = pub.venue.scopus_pct or 0.0
            raw_contrib = pct * contrib
        else:
            pts         = _core_pts(pub.venue.core_rank)
            raw_contrib = (pts / 10.0) * contrib

        raw_score += raw_contrib
        details.append(NormPubDetail(
            title=pub.title,
            author_pos=pub.author_position,
            total_authors=pub.total_authors,
            first_author=pub.first_author,
            contrib=round(contrib, 3),
            venue_label=_venue_label(pub),
            raw_contrib=round(raw_contrib, 4),
        ))

    return NormPublication(
        normalised_score=round(min(raw_score * 100, PUB_CAP), 3),
        raw_score=round(raw_score, 6),
        count=len(publications),
        details=details,
    )


# ---------------------------------------------------------------------------
# 5. Point d'entrée principal
# ---------------------------------------------------------------------------

def normalise_candidate(
    bsc_gpa:        GPAResult,
    bsc_university: Optional[UniversityResult],
    msc_gpa:        GPAResult,
    msc_university: Optional[UniversityResult],
    journal_pubs:   list[PublicationResult],
    conf_pubs:      list[PublicationResult],
) -> NormCandidate:
    """
    Normalise tous les champs d'un candidat en un seul appel.

    Retourne un NormCandidate dont les 4 scores [0..100]
    sont directement consommables par engine.py :
        candidate.bsc.academic_score
        candidate.msc.academic_score
        candidate.journals.normalised_score
        candidate.conferences.normalised_score
    """
    bsc  = norm_academic(bsc_gpa, bsc_university)
    msc  = norm_academic(msc_gpa, msc_university)
    jour = norm_publications(journal_pubs, pub_type="journal")
    conf = norm_publications(conf_pubs,    pub_type="conference")

    missing_fields = []
    if bsc.gpa.missing_flag: missing_fields.append("bsc_gpa")
    if msc.gpa.missing_flag: missing_fields.append("msc_gpa")

    needs_review = (
        bsc.gpa.needs_review
        or msc.gpa.needs_review
        or bool(missing_fields)
    )

    return NormCandidate(
        bsc=bsc, msc=msc,
        journals=jour, conferences=conf,
        needs_review=needs_review,
        missing_fields=missing_fields,
    )