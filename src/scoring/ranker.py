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
    research_score: float
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


def rank(
    results: List[ScoringResult],
    session_id: str,
    tiebreak_field: Optional[str] = None,
) -> RankingReport:
    """
    Classe les candidats selon leur score final.

    tiebreak_field: name of a ScoringResult attribute (e.g. "msc_academic",
    "journal_score", "research_score") to break ties on final_score, ahead of
    the default msc_academic -> journal_score chain. Falls back to the default
    chain if the field name is missing/invalid so a bad config value never
    breaks ranking.
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

    configured_field = (
        tiebreak_field if tiebreak_field and hasattr(results[0], tiebreak_field) else None
    )

    def _sort_key(r: ScoringResult):
        key = [-round(r.final_score, 2)]
        if configured_field:
            key.append(-(getattr(r, configured_field) or 0))
        key.append(-r.msc_academic)
        key.append(-r.journal_score)
        return tuple(key)

    sorted_res = sorted(results, key=_sort_key)

    ranked = []
    for i, r in enumerate(sorted_res):
        tiebreak_used = None
        if i > 0 and sorted_res[i-1].final_score == r.final_score:
            prev = sorted_res[i-1]
            if configured_field and getattr(prev, configured_field, None) != getattr(r, configured_field, None):
                tiebreak_used = configured_field
            elif prev.msc_academic != r.msc_academic:
                tiebreak_used = "msc_academic"
            else:
                tiebreak_used = "journal_score"

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
            research_score=r.research_score,
            bsc_gpa_norm=r.bsc_gpa_norm,
            msc_gpa_norm=r.msc_gpa_norm,
            bsc_qs_score=r.bsc_qs_score,
            msc_qs_score=r.msc_qs_score,
            justification=r.justification,
            tiebreak_used=tiebreak_used
        ))
    
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