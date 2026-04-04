from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from src.scoring.engine import ScoringResult

@dataclass
class RankedResult:
    rank: int; applicant_id: str; applicant_name: str; final_score: float; needs_review: bool; missing_fields: list
    bsc_academic: float; msc_academic: float; journal_score: float; conf_score: float
    bsc_gpa_norm: float; msc_gpa_norm: float; bsc_qs_score: float; msc_qs_score: float
    justification: str; tiebreak_used: Optional[str] = None

@dataclass
class RankingReport:
    session_id: str; generated_at: str; total_candidates: int; ranked: List[RankedResult]; score_stats: dict; needs_review_count: int

def rank(results: List[ScoringResult], session_id: str) -> RankingReport:
    # Tri complexe (Score final desc, puis tie-break)
    sorted_res = sorted(results, key=lambda r: (-round(r.final_score, 2), -r.msc_academic, -r.journal_score))
    
    ranked = []
    for i, r in enumerate(sorted_res):
        ranked.append(RankedResult(
            rank=i+1, applicant_id=r.applicant_id, applicant_name=r.applicant_name, final_score=r.final_score,
            needs_review=r.needs_review, missing_fields=r.missing_fields, bsc_academic=r.bsc_academic,
            msc_academic=r.msc_academic, journal_score=r.journal_score, conf_score=r.conf_score,
            bsc_gpa_norm=r.bsc_gpa_norm, msc_gpa_norm=r.msc_gpa_norm, bsc_qs_score=r.bsc_qs_score,
            msc_qs_score=r.msc_qs_score, justification=r.justification
        ))
    
    return RankingReport(session_id, datetime.now(timezone.utc).isoformat(), len(results), ranked, {}, sum(1 for x in results if x.needs_review))