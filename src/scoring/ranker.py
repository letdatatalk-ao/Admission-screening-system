"""

Classement final des candidats.
Reçoit une liste de ScoringResult (engine.py),
produit un classement trié avec tie-breaking, positions,
et export CSV/JSON prêts pour l'UI Streamlit et la DB.

Pipeline :
    ScoringResult[] → rank() → RankedResult[] → export_csv() / export_json()
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from io import StringIO
from typing import Optional

from src.scoring.engine import ScoringResult, RankingConfig


# ---------------------------------------------------------------------------
# Dataclasses de sortie
# ---------------------------------------------------------------------------

@dataclass
class RankedResult:
    """Un candidat classé avec sa position et ses métadonnées de tri."""
    rank:            int
    applicant_id:    Optional[str]
    applicant_name:  Optional[str]
    final_score:     float            # [0..100]
    needs_review:    bool
    missing_fields:  list[str]

    # Scores par module (pour l'affichage Streamlit)
    bsc_academic:    float
    msc_academic:    float
    journal_score:   float
    conf_score:      float

    # Scores intermédiaires (pour le détail)
    bsc_gpa_norm:    float            # [0..1]
    msc_gpa_norm:    float
    bsc_qs_score:    float            # [0..100]
    msc_qs_score:    float

    # Justification textuelle
    justification:   str

    # Tie-breaking trace (pour l'auditabilité)
    tiebreak_used:   Optional[str] = None


@dataclass
class RankingReport:
    """Rapport complet d'une session de classement."""
    session_id:      Optional[str]
    generated_at:    str                  # ISO 8601
    config:          dict                 # poids utilisés
    total_candidates: int
    ranked:          list[RankedResult]
    needs_review_count: int
    score_stats:     dict                 # min, max, mean, median


# ---------------------------------------------------------------------------
# Tie-breaking
# ---------------------------------------------------------------------------

def _tiebreak_key(r: ScoringResult) -> tuple:
    """
    Critères de départage en cas d'égalité de score final (ordre de priorité) :

    1. MSc académique       — diplôme le plus récent, le plus représentatif
    2. Journal score        — publications peer-reviewed à fort impact
    3. Conférence score     — publications peer-reviewed secondaires
    4. BSc académique       — diplôme de base
    5. Pas de données manquantes — candidat complet avant candidat incomplet
    6. applicant_id         — ordre stable déterministe (alphabétique)

    Tous les critères sont en ordre décroissant (négatif pour sorted ascending).
    """
    return (
        -r.msc_academic,
        -r.journal_score,
        -r.conf_score,
        -r.bsc_academic,
        len(r.missing_fields),          # moins de champs manquants = mieux
        r.applicant_id or "",           # ordre alphabétique comme ultime critère
    )


def _tiebreak_reason(a: ScoringResult, b: ScoringResult) -> str:
    """Produit un message explicatif du critère de départage utilisé."""
    if round(a.msc_academic, 2) != round(b.msc_academic, 2):
        return "MSc académique"
    if round(a.journal_score, 2) != round(b.journal_score, 2):
        return "score journaux"
    if round(a.conf_score, 2) != round(b.conf_score, 2):
        return "score conférences"
    if round(a.bsc_academic, 2) != round(b.bsc_academic, 2):
        return "BSc académique"
    if len(a.missing_fields) != len(b.missing_fields):
        return "complétude du dossier"
    return "ordre alphabétique (ID)"


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------

def _compute_stats(scores: list[float]) -> dict:
    """Calcule min, max, moyenne, médiane sur la liste des scores finaux."""
    if not scores:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "count": 0}

    n      = len(scores)
    sorted_s = sorted(scores)
    mean   = round(sum(sorted_s) / n, 2)
    mid    = n // 2
    median = sorted_s[mid] if n % 2 else round(
        (sorted_s[mid - 1] + sorted_s[mid]) / 2, 2
    )
    return {
        "min":    round(sorted_s[0], 2),
        "max":    round(sorted_s[-1], 2),
        "mean":   mean,
        "median": median,
        "count":  n,
    }


# ---------------------------------------------------------------------------
# Fonction principale de classement
# ---------------------------------------------------------------------------

def rank(
    results:    list[ScoringResult],
    session_id: Optional[str] = None,
    top_n:      Optional[int] = None,
) -> RankingReport:
    """
    Trie les candidats par score décroissant avec tie-breaking déterministe.

    Args:
        results    : liste de ScoringResult produits par engine.compute_score()
        session_id : identifiant de la session (pour la DB et les logs)
        top_n      : si fourni, ne retourne que les N premiers candidats

    Returns:
        RankingReport : classement complet + statistiques + métadonnées

    Tie-breaking (en cas d'égalité de score final arrondi à 2 décimales) :
        1. MSc académique  2. Journaux  3. Conférences
        4. BSc académique  5. Complétude du dossier  6. ID alphabétique

    Usage :
        report = rank(results, session_id="sess_2026_01", top_n=10)
        print(report.ranked[0].applicant_name, report.ranked[0].final_score)
    """
    if not results:
        return RankingReport(
            session_id=session_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            config={},
            total_candidates=0,
            ranked=[],
            needs_review_count=0,
            score_stats=_compute_stats([]),
        )

    # Tri principal : score décroissant + tie-breaking déterministe
    sorted_results = sorted(
        results,
        key=lambda r: (-round(r.final_score, 2), _tiebreak_key(r))
    )

    # Détection des ex-aequo pour annoter la trace
    ranked: list[RankedResult] = []
    for i, r in enumerate(sorted_results):
        # Cherche si le candidat précédent avait le même score arrondi
        tiebreak = None
        if i > 0:
            prev = sorted_results[i - 1]
            if round(prev.final_score, 2) == round(r.final_score, 2):
                tiebreak = _tiebreak_reason(prev, r)

        ranked.append(RankedResult(
            rank=i + 1,
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
            tiebreak_used=tiebreak,
        ))

    # Limiter à top_n si demandé
    if top_n:
        ranked = ranked[:top_n]

    # Config snapshot (pour le rapport)
    config_snapshot = {}
    if results:
        cfg = results[0].config_used
        config_snapshot = {
            "w_bsc":  cfg.w_bsc,
            "w_msc":  cfg.w_msc,
            "w_jour": cfg.w_jour,
            "w_conf": cfg.w_conf,
        }

    all_scores = [r.final_score for r in sorted_results]

    return RankingReport(
        session_id=session_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        config=config_snapshot,
        total_candidates=len(results),
        ranked=ranked,
        needs_review_count=sum(1 for r in ranked if r.needs_review),
        score_stats=_compute_stats(all_scores),
    )


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def export_csv(report: RankingReport) -> str:
    """
    Exporte le classement en CSV (string).
    Colonnes : rank, id, name, score, bsc, msc, journaux, conf,
               needs_review, missing_fields, tiebreak_used

    Usage :
        csv_str = export_csv(report)
        with open("ranking.csv", "w") as f:
            f.write(csv_str)

        # Ou directement dans Streamlit :
        st.download_button("Télécharger CSV", csv_str, "ranking.csv")
    """
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "rank", "applicant_id", "applicant_name",
        "final_score",
        "bsc_academic", "msc_academic", "journal_score", "conf_score",
        "bsc_gpa_norm", "msc_gpa_norm", "bsc_qs_score", "msc_qs_score",
        "needs_review", "missing_fields", "tiebreak_used",
    ])

    for r in report.ranked:
        writer.writerow([
            r.rank,
            r.applicant_id or "",
            r.applicant_name or "",
            f"{r.final_score:.2f}",
            f"{r.bsc_academic:.2f}",
            f"{r.msc_academic:.2f}",
            f"{r.journal_score:.2f}",
            f"{r.conf_score:.2f}",
            f"{r.bsc_gpa_norm:.4f}",
            f"{r.msc_gpa_norm:.4f}",
            f"{r.bsc_qs_score:.2f}",
            f"{r.msc_qs_score:.2f}",
            r.needs_review,
            "|".join(r.missing_fields) if r.missing_fields else "",
            r.tiebreak_used or "",
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Export JSON
# ---------------------------------------------------------------------------

def export_json(report: RankingReport, indent: int = 2) -> str:
    """
    Exporte le rapport complet en JSON (string).
    Inclut les métadonnées, statistiques et justifications.

    Usage :
        json_str = export_json(report)
        with open("ranking.json", "w") as f:
            f.write(json_str)
    """
    payload = {
        "session_id":        report.session_id,
        "generated_at":      report.generated_at,
        "config":            report.config,
        "total_candidates":  report.total_candidates,
        "needs_review_count": report.needs_review_count,
        "score_stats":       report.score_stats,
        "ranked": [
            {
                "rank":           r.rank,
                "applicant_id":   r.applicant_id,
                "applicant_name": r.applicant_name,
                "final_score":    r.final_score,
                "modules": {
                    "bsc_academic":  r.bsc_academic,
                    "msc_academic":  r.msc_academic,
                    "journal_score": r.journal_score,
                    "conf_score":    r.conf_score,
                },
                "details": {
                    "bsc_gpa_norm": r.bsc_gpa_norm,
                    "msc_gpa_norm": r.msc_gpa_norm,
                    "bsc_qs_score": r.bsc_qs_score,
                    "msc_qs_score": r.msc_qs_score,
                },
                "needs_review":   r.needs_review,
                "missing_fields": r.missing_fields,
                "tiebreak_used":  r.tiebreak_used,
                "justification":  r.justification,
            }
            for r in report.ranked
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# Affichage console (debug / notebook)
# ---------------------------------------------------------------------------

def print_ranking(report: RankingReport, show_justification: bool = False) -> None:
    """
    Affiche le classement dans le terminal.
    Utile pour les notebooks de validation et les tests.

    Usage :
        print_ranking(report)
        print_ranking(report, show_justification=True)
    """
    print(f"\n{'='*62}")
    print(f"  Classement — session : {report.session_id or 'N/A'}")
    print(f"  Généré le : {report.generated_at}")
    print(f"  Candidats : {report.total_candidates} | "
          f"Revue requise : {report.needs_review_count}")
    stats = report.score_stats
    print(f"  Scores — min:{stats['min']:.1f}  max:{stats['max']:.1f}  "
          f"moy:{stats['mean']:.1f}  med:{stats['median']:.1f}")
    print(f"{'='*62}")
    print(f"  {'#':<4} {'Nom':<28} {'Score':>6}  "
          f"{'BSc':>5} {'MSc':>5} {'JP':>5} {'CP':>5}  {'⚠'}")
    print(f"  {'-'*58}")

    for r in report.ranked:
        review_flag = "⚠" if r.needs_review else ""
        tie_flag    = f" [tie→{r.tiebreak_used}]" if r.tiebreak_used else ""
        name        = (r.applicant_name or r.applicant_id or "?")[:27]
        print(
            f"  {r.rank:<4} {name:<28} {r.final_score:>6.2f}  "
            f"{r.bsc_academic:>5.1f} {r.msc_academic:>5.1f} "
            f"{r.journal_score:>5.1f} {r.conf_score:>5.1f}  "
            f"{review_flag}{tie_flag}"
        )
        if show_justification:
            for line in r.justification.split("\n")[1:]:
                print(f"       {line}")

    print(f"{'='*62}\n")