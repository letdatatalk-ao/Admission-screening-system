"""
src/scoring/engine.py

Moteur de scoring composite.
Reçoit un NormCandidate (normalizer.py) + un RankingConfig (poids),
produit un ScoringResult avec le score final sur 100 et la justification
complète par module — prêt pour ranker.py et l'UI Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.scoring.normalizer import NormCandidate


# ---------------------------------------------------------------------------
# Configuration des poids (RankingConfig)
# ---------------------------------------------------------------------------

@dataclass
class RankingConfig:
    """
    Poids de chaque module en pourcentage.
    La somme DOIT être égale à 100.0 — validate() lève ValueError sinon.

    Poids par défaut  :
        BSc         15%
        MSc         25%
        Journaux    35%
        Conférences 25%
    """
    w_bsc:  float = 15.0
    w_msc:  float = 25.0
    w_jour: float = 35.0
    w_conf: float = 25.0

    def validate(self) -> None:
        total = round(self.w_bsc + self.w_msc + self.w_jour + self.w_conf, 6)
        if abs(total - 100.0) > 0.01:
            raise ValueError(
                f"RankingConfig : la somme des poids doit être 100.0, "
                f"reçu {total:.4f}"
            )

    @property
    def as_fractions(self) -> dict[str, float]:
        """Retourne les poids en fractions [0..1] pour le calcul."""
        return {
            "bsc":  self.w_bsc  / 100.0,
            "msc":  self.w_msc  / 100.0,
            "jour": self.w_jour / 100.0,
            "conf": self.w_conf / 100.0,
        }


# Profils prédéfinis — utilisables directement ou comme base d'ajustement
CONFIG_DEFAULT = RankingConfig(15.0, 25.0, 35.0, 25.0)   # orienté recherche
CONFIG_ACADEMIC = RankingConfig(25.0, 35.0, 25.0, 15.0)  # orienté académique pur
CONFIG_RESEARCH = RankingConfig(10.0, 15.0, 45.0, 30.0)  # orienté publication


# ---------------------------------------------------------------------------
# Dataclasses de sortie
# ---------------------------------------------------------------------------

@dataclass
class ModuleScore:
    """Score d'un module individuel avec sa contribution au score final."""
    name:          str
    raw_score:     float   # score normalisé [0..100] avant pondération
    weight:        float   # poids en fraction [0..1]
    contribution:  float   # raw_score × weight → contribution au total
    missing:       bool    # True si donnée absente (score = 0 par défaut)
    flag:          Optional[str] = None   # message d'alerte si anomalie


@dataclass
class ScoringResult:
    """
    Résultat complet du scoring d'un candidat.
    Consommé par ranker.py et l'UI Streamlit.
    """
    # Identité
    applicant_id:    Optional[str]
    applicant_name:  Optional[str]

    # Score final
    final_score:     float          # [0..100], arrondi à 2 décimales
    config_used:     RankingConfig

    # Détail par module
    modules:         list[ModuleScore]

    # Flags qualité
    needs_review:    bool
    missing_fields:  list[str]

    # Justification textuelle (pour l'UI et les logs)
    justification:   str

    # Snapshot des scores intermédiaires (pour debug et DB)
    bsc_academic:    float
    msc_academic:    float
    journal_score:   float
    conf_score:      float
    bsc_gpa_norm:    float          # gpa_score [0..1]
    msc_gpa_norm:    float
    bsc_qs_score:    float          # [0..100]
    msc_qs_score:    float


# ---------------------------------------------------------------------------
# Fonctions internes
# ---------------------------------------------------------------------------

def _build_justification(modules: list[ModuleScore], final: float,
                          needs_review: bool, missing: list[str]) -> str:
    """
    Produit une justification textuelle lisible par un comité.
    Format :
        Score final : 73.45 / 100
        ├─ BSc académique   : 82.0  × 15% = 12.30 pts
        ├─ MSc académique   : 91.5  × 25% = 22.88 pts
        ├─ Journaux         : 65.0  × 35% = 22.75 pts
        └─ Conférences      : 50.0  × 25% = 12.50 pts
        ⚠ Revue humaine recommandée : bsc_gpa absent
    """
    lines = [f"Score final : {final:.2f} / 100"]
    for i, m in enumerate(modules):
        prefix = "└─" if i == len(modules) - 1 else "├─"
        flag   = f"  [{m.flag}]" if m.flag else ""
        missing_mark = " ⚠ ABSENT" if m.missing else ""
        lines.append(
            f"  {prefix} {m.name:<22} : "
            f"{m.raw_score:>6.2f} × {m.weight*100:.0f}% "
            f"= {m.contribution:>5.2f} pts"
            f"{missing_mark}{flag}"
        )
    if needs_review:
        reason = ", ".join(missing) if missing else "anomalie détectée"
        lines.append(f"  ⚠ Revue humaine recommandée : {reason}")
    return "\n".join(lines)


def _module_flag(name: str, norm: NormCandidate) -> Optional[str]:
    """Retourne un flag d'alerte si le module a une anomalie."""
    if name == "bsc":
        if norm.bsc.gpa.scale_inferred:
            return f"échelle GPA inférée ({norm.bsc.gpa.source})"
        if norm.bsc.gpa.clamped:
            return "GPA clampé à 4.0"
        if norm.bsc.qs_unranked:
            return "université non classée QS"
    if name == "msc":
        if norm.msc.gpa.scale_inferred:
            return f"échelle GPA inférée ({norm.msc.gpa.source})"
        if norm.msc.gpa.clamped:
            return "GPA clampé à 4.0"
        if norm.msc.qs_unranked:
            return "université non classée QS"
    return None


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def compute_score(
    norm:           NormCandidate,
    config:         RankingConfig = CONFIG_DEFAULT,
    applicant_id:   Optional[str] = None,
    applicant_name: Optional[str] = None,
) -> ScoringResult:
    """
    Calcule le score composite d'un candidat.

    Formule :
        Score = w_bsc  × academic_bsc
              + w_msc  × academic_msc
              + w_jour × journal_score
              + w_conf × conf_score

    Chaque score est sur [0..100], les poids sont en fractions [0..1].
    Le résultat final est donc sur [0..100].

    Args:
        norm           : NormCandidate produit par normalizer.normalise_candidate()
        config         : RankingConfig avec les poids (somme = 100%)
        applicant_id   : identifiant candidat (pour la DB)
        applicant_name : nom lisible (pour les logs et l'UI)

    Returns:
        ScoringResult  : score final + détail + justification
    """
    config.validate()
    w = config.as_fractions

    # ── Scores intermédiaires ────────────────────────────────────────────────
    bsc_score  = norm.bsc.academic_score          # [0..100]
    msc_score  = norm.msc.academic_score          # [0..100]
    jour_score = norm.journals.normalised_score   # [0..100]
    conf_score = norm.conferences.normalised_score # [0..100]

    # ── Modules ─────────────────────────────────────────────────────────────
    modules = [
        ModuleScore(
            name="BSc académique",
            raw_score=round(bsc_score, 3),
            weight=w["bsc"],
            contribution=round(bsc_score * w["bsc"], 4),
            missing="bsc_gpa" in norm.missing_fields,
            flag=_module_flag("bsc", norm),
        ),
        ModuleScore(
            name="MSc académique",
            raw_score=round(msc_score, 3),
            weight=w["msc"],
            contribution=round(msc_score * w["msc"], 4),
            missing="msc_gpa" in norm.missing_fields,
            flag=_module_flag("msc", norm),
        ),
        ModuleScore(
            name="Journaux (Scopus)",
            raw_score=round(jour_score, 3),
            weight=w["jour"],
            contribution=round(jour_score * w["jour"], 4),
            missing=False,   # 0 publication n'est pas une donnée manquante
            flag=None,
        ),
        ModuleScore(
            name="Conférences (CORE)",
            raw_score=round(conf_score, 3),
            weight=w["conf"],
            contribution=round(conf_score * w["conf"], 4),
            missing=False,
            flag=None,
        ),
    ]

    # ── Score final ──────────────────────────────────────────────────────────
    final_score = round(sum(m.contribution for m in modules), 2)

    # ── Justification ────────────────────────────────────────────────────────
    justification = _build_justification(
        modules, final_score, norm.needs_review, norm.missing_fields
    )

    return ScoringResult(
        applicant_id=applicant_id,
        applicant_name=applicant_name,
        final_score=final_score,
        config_used=config,
        modules=modules,
        needs_review=norm.needs_review,
        missing_fields=norm.missing_fields,
        justification=justification,
        bsc_academic=bsc_score,
        msc_academic=msc_score,
        journal_score=jour_score,
        conf_score=conf_score,
        bsc_gpa_norm=norm.bsc.gpa.gpa_score,
        msc_gpa_norm=norm.msc.gpa.gpa_score,
        bsc_qs_score=norm.bsc.qs_score,
        msc_qs_score=norm.msc.qs_score,
    )


# ---------------------------------------------------------------------------
# Scoring batch (liste de candidats)
# ---------------------------------------------------------------------------

def compute_scores_batch(
    candidates: list[tuple[NormCandidate, Optional[str], Optional[str]]],
    config:     RankingConfig = CONFIG_DEFAULT,
) -> list[ScoringResult]:
    """
    Calcule les scores d'une liste de candidats en un appel.

    Args:
        candidates : liste de tuples (NormCandidate, applicant_id, applicant_name)
        config     : configuration de poids partagée pour tous

    Returns:
        Liste de ScoringResult dans le même ordre que l'entrée.

    Usage :
        results = compute_scores_batch([
            (norm_esra,   "001", "Esra Al-Nashash"),
            (norm_devon,  "002", "Devon Serrao"),
            (norm_ahmed,  "003", "Ahmed Khalil"),
        ])
    """
    config.validate()
    return [
        compute_score(norm, config, aid, aname)
        for norm, aid, aname in candidates
    ]