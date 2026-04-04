from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from src.scoring.normalizer import NormCandidate, to_float

@dataclass
class RankingConfig:
    w_bsc: float = 15.0; w_msc: float = 25.0; w_jour: float = 35.0; w_conf: float = 25.0
    
    def validate(self) -> None:
        total = round(to_float(self.w_bsc) + to_float(self.w_msc) + to_float(self.w_jour) + to_float(self.w_conf), 2)
        if abs(total - 100.0) > 0.5: raise ValueError(f"Sum must be 100, got {total}")

    @property
    def as_fractions(self) -> dict[str, float]:
        return {"bsc": to_float(self.w_bsc)/100.0, "msc": to_float(self.w_msc)/100.0, "jour": to_float(self.w_jour)/100.0, "conf": to_float(self.w_conf)/100.0}

    @classmethod
    def from_db_weights(cls, weights: dict) -> "RankingConfig":
        total = sum(to_float(v) for v in weights.values())
        mult = 100 if total <= 4.0 else 1 # Détection auto fraction vs %
        return cls(to_float(weights.get("w_bsc", 15))*mult, to_float(weights.get("w_msc", 25))*mult, 
                   to_float(weights.get("w_journals", 35))*mult, to_float(weights.get("w_conferences", 25))*mult)

@dataclass
class ScoringResult:
    applicant_id: str; applicant_name: str; final_score: float; bsc_academic: float; msc_academic: float
    journal_score: float; conf_score: float; needs_review: bool
    missing_fields: list = field(default_factory=list); config_used: Optional[RankingConfig] = None
    bsc_gpa_norm: float = 0.0; msc_gpa_norm: float = 0.0; bsc_qs_score: float = 0.0; msc_qs_score: float = 0.0
    justification: str = ""

def compute_score(norm: NormCandidate, config: RankingConfig, aid: str, aname: str) -> ScoringResult:
    config.validate(); f = config.as_fractions
    final = round(to_float(norm.bsc.academic_score)*f["bsc"] + to_float(norm.msc.academic_score)*f["msc"] + 
                  to_float(norm.journals.normalised_score)*f["jour"] + to_float(norm.conferences.normalised_score)*f["conf"], 2)
    return ScoringResult(aid, aname, final, float(norm.bsc.academic_score), float(norm.msc.academic_score), 
                         float(norm.journals.normalised_score), float(norm.conferences.normalised_score), 
                         norm.needs_review, norm.missing_fields, config, norm.bsc.gpa.gpa_score, 
                         norm.msc.gpa.gpa_score, norm.bsc.qs_score, norm.msc.qs_score, f"Weighted score: {final}/100")

def compute_scores_batch(candidates: list[tuple], config: RankingConfig) -> list[ScoringResult]:
    return [compute_score(c[0], config, c[1], c[2]) for c in candidates]