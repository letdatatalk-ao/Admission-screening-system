from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from src.scoring.normalizer import NormCandidate, to_float


@dataclass
class RankingConfig:
    """Configuration des pondérations - TOUJOURS en pourcentages (somme = 100)."""
    w_bsc: float = 15.0
    w_msc: float = 25.0
    w_jour: float = 35.0
    w_conf: float = 25.0
    
    def validate(self) -> None:
        total = round(to_float(self.w_bsc, 0) + to_float(self.w_msc, 0) + 
                      to_float(self.w_jour, 0) + to_float(self.w_conf, 0), 2)
        if abs(total - 100.0) > 0.5:
            raise ValueError(f"Sum of weights must be 100, got {total}")

    @property
    def as_fractions(self) -> dict[str, float]:
        return {
            "bsc": to_float(self.w_bsc, 0) / 100.0,
            "msc": to_float(self.w_msc, 0) / 100.0,
            "jour": to_float(self.w_jour, 0) / 100.0,
            "conf": to_float(self.w_conf, 0) / 100.0
        }

    @classmethod
    def from_db_weights(cls, weights: dict) -> "RankingConfig":
        w_bsc = to_float(weights.get("w_bsc", 15.0), 15.0)
        w_msc = to_float(weights.get("w_msc", 25.0), 25.0)
        w_jour = to_float(weights.get("w_journals", 35.0), 35.0)
        w_conf = to_float(weights.get("w_conferences", 25.0), 25.0)
        
        total = w_bsc + w_msc + w_jour + w_conf
        
        if 0.9 < total < 1.1:
            w_bsc *= 100
            w_msc *= 100
            w_jour *= 100
            w_conf *= 100
        
        return cls(w_bsc, w_msc, w_jour, w_conf)


@dataclass
class ScoringResult:
    applicant_id: str
    applicant_name: str
    final_score: float
    bsc_academic: float
    msc_academic: float
    journal_score: float
    conf_score: float
    needs_review: bool
    missing_fields: list = field(default_factory=list)
    config_used: Optional[RankingConfig] = None
    bsc_gpa_norm: float = 0.0
    msc_gpa_norm: float = 0.0
    bsc_qs_score: float = 0.0
    msc_qs_score: float = 0.0
    justification: str = ""
    
    @property
    def detailed_justification(self) -> str:
        if not self.config_used:
            return self.justification
        f = self.config_used.as_fractions
        return (
            f"Score = BSc({self.bsc_academic:.1f}) × {f['bsc']*100:.0f}% + "
            f"MSc({self.msc_academic:.1f}) × {f['msc']*100:.0f}% + "
            f"Journaux({self.journal_score:.1f}) × {f['jour']*100:.0f}% + "
            f"Conférences({self.conf_score:.1f}) × {f['conf']*100:.0f}% = {self.final_score:.2f}/100"
        )


def compute_score(norm: NormCandidate, config: RankingConfig, aid: str, aname: str) -> ScoringResult:
    """Calcule le score final d'un candidat selon la configuration."""
    config.validate()
    f = config.as_fractions
    
    final = round(
        to_float(norm.bsc.academic_score, 0) * f["bsc"] +
        to_float(norm.msc.academic_score, 0) * f["msc"] +
        to_float(norm.journals.normalised_score, 0) * f["jour"] +
        to_float(norm.conferences.normalised_score, 0) * f["conf"],
        2
    )
    
    return ScoringResult(
        aid, aname, final,
        float(norm.bsc.academic_score),
        float(norm.msc.academic_score),
        float(norm.journals.normalised_score),
        float(norm.conferences.normalised_score),
        norm.needs_review,
        norm.missing_fields,
        config,
        norm.bsc.gpa.gpa_score,
        norm.msc.gpa.gpa_score,
        norm.bsc.qs_score,
        norm.msc.qs_score,
        f"Weighted score: {final:.2f}/100"
    )


def compute_scores_batch(candidates: list[tuple], config: RankingConfig) -> list[ScoringResult]:
    """Calcule les scores pour un lot de candidats."""
    return [compute_score(c[0], config, c[1], c[2]) for c in candidates]