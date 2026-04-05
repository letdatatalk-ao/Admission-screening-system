from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
import statistics
from src.scoring.engine import ScoringResult

@dataclass
class RankedResult:
    rank: int
    applicant_id: str
    applicant_name: str
    final_score: float
    needs_review: bool
    missing_fields: list
    bsc_academic: float
    msc_academic: float
    journal_score: float
    conf_score: float
    bsc_gpa_norm: float
    msc_gpa_norm: float
    bsc_qs_score: float
    msc_qs_score: float
    justification: str
    tiebreak_used: Optional[str] = None


@dataclass
class RankingReport:
    session_id: str
    generated_at: str
    total_candidates: int
    ranked: List[RankedResult]
    score_stats: dict
    needs_review_count: int


def rank(results: List[ScoringResult], session_id: str) -> RankingReport:
    """
    Classe les candidats selon leur score final.
    Gère les égalités avec tie-break sur MSc academic puis journal score.
    """
    if not results:
        return RankingReport(
            session_id=session_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_candidates=0,
            ranked=[],
            score_stats={"min": 0, "max": 0, "mean": 0, "median": 0, "std": 0},
            needs_review_count=0
        )
    
    # Tri complexe (Score final desc, puis tie-break)
    sorted_res = sorted(
        results, 
        key=lambda r: (
            -round(r.final_score, 2),   # Score final décroissant
            -r.msc_academic,            # Tie-break 1: MSc academic
            -r.journal_score            # Tie-break 2: Journal score
        )
    )
    
    ranked = []
    for i, r in enumerate(sorted_res):
        # Déterminer le tie-break utilisé
        tiebreak_used = None
        if i > 0 and sorted_res[i-1].final_score == r.final_score:
            if sorted_res[i-1].msc_academic == r.msc_academic:
                tiebreak_used = "journal_score"
            else:
                tiebreak_used = "msc_academic"
        
        ranked.append(RankedResult(
            rank=i+1,
            applicant_id=r.applicant_id,
            applicant_name=r.applicant_name,
            final_score=r.final_score,
            needs_review=r.needs_review,
            missing_fields=r.missing_fields,
            bsc_academic=r.bsc_academic,
            msc_academic=r.msc_academic,
            journal_score=r.journal_score,
            conf_score=r.conf_score,
            bsc_gpa_norm=r.bsc_gpa_norm,
            msc_gpa_norm=r.msc_gpa_norm,
            bsc_qs_score=r.bsc_qs_score,
            msc_qs_score=r.msc_qs_score,
            justification=r.justification,
            tiebreak_used=tiebreak_used
        ))
    
    # Calcul des statistiques des scores
    scores = [r.final_score for r in results]
    score_stats = {
        "min": round(min(scores), 2),
        "max": round(max(scores), 2),
        "mean": round(statistics.mean(scores), 2),
        "median": round(statistics.median(scores), 2),
        "std": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0
    }
    
    return RankingReport(
        session_id=session_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_candidates=len(results),
        ranked=ranked,
        score_stats=score_stats,
        needs_review_count=sum(1 for x in results if x.needs_review)
    )