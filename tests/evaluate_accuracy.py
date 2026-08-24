#!/usr/bin/env python3
"""
tests/evaluate_accuracy.py

Compare extracted results against data/ground_truth.csv.

Two modes:
  1. Run extraction then evaluate:
       python -m tests.evaluate_accuracy --run
  2. Evaluate a previously saved results JSON:
       python -m tests.evaluate_accuracy --results results.json

Ground truth CSV columns:
  applicant_id, full_name, bsc_uni_name, bsc_qs_rank, msc_uni_name, msc_qs_rank,
  bsc_gpa_raw, bsc_gpa_scale, msc_gpa_raw, msc_gpa_scale,
  cp1_conference, cp1_core_ranking, cp1_first_author, notes

  applicant_id in ground truth maps to archive file IDs via 'full_name' matching
  or via an explicit id_map.csv if present.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Force UTF-8 output — the report prints unicode icons (checkmarks, etc.)
# that crash under Windows' default cp1252 console encoding.
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import pandas as pd
from rapidfuzz import fuzz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

GROUND_TRUTH_PATH = PROJECT_ROOT / "data" / "ground_truth.csv"
ARCHIVE_DIR = PROJECT_ROOT / "archive"


# ─────────────────────────────────────────────────────────────────────────────
# Ground truth loading
# ─────────────────────────────────────────────────────────────────────────────

def load_ground_truth() -> pd.DataFrame:
    df = pd.read_csv(GROUND_TRUTH_PATH, dtype=str)
    # Normalize NULL strings and empty/NaN cells → Python None
    df = df.where(df != "NULL", other=None)
    df = df.where(pd.notnull(df), None)
    # Convert numeric fields
    for col in ["bsc_qs_rank", "msc_qs_rank", "bsc_gpa_raw", "bsc_gpa_scale",
                "msc_gpa_raw", "msc_gpa_scale"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "cp1_first_author" in df.columns:
        df["cp1_first_author"] = df["cp1_first_author"].str.upper().map(
            {"TRUE": True, "FALSE": False}
        )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Field comparators
# ─────────────────────────────────────────────────────────────────────────────

def _name_match(extracted: Optional[str], ground: Optional[str],
                threshold: int = 75) -> bool:
    """Fuzzy university/conference name match."""
    if ground is None:
        return True  # no ground truth to compare
    if extracted is None:
        return False
    score = fuzz.token_set_ratio(extracted.lower(), ground.lower())
    return score >= threshold


def _is_missing(v) -> bool:
    """True for None or pandas/numpy NaN (pd.to_numeric coercion reintroduces
    NaN even after the DataFrame-wide None normalisation in load_ground_truth)."""
    return v is None or (isinstance(v, float) and pd.isna(v))


def _gpa_match(extracted: Optional[float], ground: Optional[float],
               tolerance: float = 0.1) -> bool:
    """GPA raw value match within ±tolerance."""
    if _is_missing(ground):
        return True  # no ground truth
    if _is_missing(extracted):
        return False
    return abs(float(extracted) - float(ground)) <= tolerance


def _rank_match(extracted: Optional[int], ground: Optional[int],
                tolerance_pct: float = 0.10) -> bool:
    """QS rank match within ±10%."""
    if _is_missing(ground):
        return True
    if _is_missing(extracted):
        return False
    margin = max(10, int(float(ground) * tolerance_pct))
    return abs(int(extracted) - int(ground)) <= margin


# ─────────────────────────────────────────────────────────────────────────────
# Per-candidate evaluation
# ─────────────────────────────────────────────────────────────────────────────

FIELDS = [
    "bsc_uni",
    "msc_uni",
    "bsc_gpa_raw",
    "msc_gpa_raw",
    "bsc_qs_rank",
    "msc_qs_rank",
    "cp1_conference",
    "cp1_first_author",
]


def evaluate_candidate(extracted: dict, gt_row: pd.Series) -> dict:
    """
    Compare one extracted result against one ground-truth row.
    Returns a dict with per-field pass/fail and an overall accuracy score.
    """
    results = {}

    # BSc university
    results["bsc_uni"] = _name_match(extracted.get("bsc_uni"), gt_row.get("bsc_uni_name"))

    # MSc university
    results["msc_uni"] = _name_match(extracted.get("msc_uni"), gt_row.get("msc_uni_name"))

    # BSc GPA
    results["bsc_gpa_raw"] = _gpa_match(
        extracted.get("bsc_gpa_raw"), gt_row.get("bsc_gpa_raw")
    )

    # MSc GPA
    results["msc_gpa_raw"] = _gpa_match(
        extracted.get("msc_gpa_raw"), gt_row.get("msc_gpa_raw")
    )

    # QS ranks
    results["bsc_qs_rank"] = _rank_match(
        extracted.get("bsc_qs_rank"), gt_row.get("bsc_qs_rank")
    )
    results["msc_qs_rank"] = _rank_match(
        extracted.get("msc_qs_rank"), gt_row.get("msc_qs_rank")
    )

    # Conference (cp1)
    gt_conf = gt_row.get("cp1_conference")
    if gt_conf:
        pubs = extracted.get("publications", [])
        conf_found = any(
            _name_match(p.get("venue"), gt_conf, threshold=70)
            for p in pubs
            if p.get("pub_type") == "conference"
        )
        # Also check titles
        if not conf_found:
            conf_found = any(
                _name_match(p.get("title"), gt_conf, threshold=65)
                for p in pubs
            )
        results["cp1_conference"] = conf_found
    else:
        results["cp1_conference"] = True  # no ground truth

    # cp1 first author
    gt_fa = gt_row.get("cp1_first_author")
    if gt_fa is not None and gt_conf:
        pubs = extracted.get("publications", [])
        matched = [
            p for p in pubs
            if _name_match(p.get("venue"), gt_conf, threshold=70)
            or _name_match(p.get("title"), gt_conf, threshold=65)
        ]
        if matched:
            extracted_fa = matched[0].get("author_position") == 1
            results["cp1_first_author"] = extracted_fa == bool(gt_fa)
        else:
            results["cp1_first_author"] = False
    else:
        results["cp1_first_author"] = True  # no ground truth

    # Fields that have real ground truth values
    evaluable = [f for f in FIELDS if _has_ground_truth(gt_row, f)]
    if evaluable:
        accuracy = sum(results[f] for f in evaluable) / len(evaluable)
    else:
        accuracy = None

    return {
        "field_results": results,
        "evaluable_fields": evaluable,
        "accuracy": accuracy,
    }


def _has_ground_truth(gt_row: pd.Series, field: str) -> bool:
    mapping = {
        "bsc_uni":        "bsc_uni_name",
        "msc_uni":        "msc_uni_name",
        "bsc_gpa_raw":    "bsc_gpa_raw",
        "msc_gpa_raw":    "msc_gpa_raw",
        "bsc_qs_rank":    "bsc_qs_rank",
        "msc_qs_rank":    "msc_qs_rank",
        "cp1_conference": "cp1_conference",
        "cp1_first_author": "cp1_first_author",
    }
    col = mapping.get(field)
    if col is None:
        return False
    val = gt_row.get(col)
    return val is not None and str(val).strip() not in ("", "nan", "None")


# ─────────────────────────────────────────────────────────────────────────────
# Matching extracted results to ground truth
# ─────────────────────────────────────────────────────────────────────────────

def match_to_ground_truth(results: list, gt: pd.DataFrame) -> list:
    """
    Match extracted results to ground truth rows.
    Strategy:
      1. Try exact applicant_id match (if gt has archive IDs)
      2. Fuzzy full_name match
    Returns list of (extracted_dict, gt_row_or_None).
    """
    matched = []
    unmatched_gt = set(gt.index)

    for r in results:
        aid = r.get("id", "")
        name = r.get("full_name", "") or ""

        # Strategy 1: direct id match
        id_rows = gt[gt["applicant_id"] == aid]
        if not id_rows.empty:
            matched.append((r, id_rows.iloc[0]))
            unmatched_gt.discard(id_rows.index[0])
            continue

        # Strategy 2: fuzzy name match
        best_score = 0
        best_row = None
        best_idx = None
        for idx, row in gt.iterrows():
            gt_name = str(row.get("full_name", "") or "")
            if not gt_name:
                continue
            score = fuzz.token_set_ratio(name.lower(), gt_name.lower())
            if score > best_score:
                best_score = score
                best_row = row
                best_idx = idx

        if best_score >= 75 and best_row is not None:
            matched.append((r, best_row))
            unmatched_gt.discard(best_idx)
        else:
            matched.append((r, None))

    return matched


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def print_report(pairs: list) -> None:
    print(f"\n{'='*70}")
    print("ACCURACY REPORT — Ground Truth Comparison")
    print(f"{'='*70}")

    all_field_scores = {f: [] for f in FIELDS}
    overall_accuracies = []

    for extracted, gt_row in pairs:
        aid = extracted.get("id", "?")
        name = extracted.get("full_name", "?")

        if gt_row is None:
            print(f"\n  {aid} ({name}): no ground truth match — skipped")
            continue

        gt_name = gt_row.get("full_name", "?")
        eval_result = evaluate_candidate(extracted, gt_row)
        acc = eval_result["accuracy"]
        evaluable = eval_result["evaluable_fields"]
        field_r = eval_result["field_results"]

        acc_str = f"{acc*100:.1f}%" if acc is not None else "N/A"
        print(f"\n  {aid} ({name})")
        print(f"    GT match: {gt_name}")
        print(f"    Accuracy: {acc_str}  [{len(evaluable)} evaluable fields]")

        for f in evaluable:
            icon = "✅" if field_r[f] else "❌"
            gt_col = {
                "bsc_uni": "bsc_uni_name", "msc_uni": "msc_uni_name",
                "bsc_gpa_raw": "bsc_gpa_raw", "msc_gpa_raw": "msc_gpa_raw",
                "bsc_qs_rank": "bsc_qs_rank", "msc_qs_rank": "msc_qs_rank",
                "cp1_conference": "cp1_conference", "cp1_first_author": "cp1_first_author",
            }.get(f, f)
            gt_val = gt_row.get(gt_col)
            ex_val = _get_extracted_field(extracted, f)
            print(f"    {icon} {f:<20} GT={str(gt_val):<25} extracted={ex_val}")
            all_field_scores[f].append(1 if field_r[f] else 0)

        if acc is not None:
            overall_accuracies.append(acc)

    # Aggregate stats
    print(f"\n{'─'*70}")
    print("AGGREGATE ACCURACY")
    print(f"{'─'*70}")

    for f in FIELDS:
        scores = all_field_scores[f]
        if scores:
            pct = 100 * sum(scores) / len(scores)
            bar = "█" * int(pct / 5)
            print(f"  {f:<22} {pct:5.1f}%  {bar}")

    if overall_accuracies:
        mean_acc = 100 * sum(overall_accuracies) / len(overall_accuracies)
        print(f"\n  Overall mean accuracy: {mean_acc:.1f}%")
        target = 90.0
        icon = "✅" if mean_acc >= target else "❌"
        print(f"  {icon} Target ≥{target:.0f}%: {'PASSED' if mean_acc >= target else 'NOT YET'}")
    else:
        print("  No candidates with ground truth matched.")


def _get_extracted_field(extracted: dict, field: str):
    mapping = {
        "bsc_uni":          lambda r: r.get("bsc_uni"),
        "msc_uni":          lambda r: r.get("msc_uni"),
        "bsc_gpa_raw":      lambda r: r.get("bsc_gpa_raw"),
        "msc_gpa_raw":      lambda r: r.get("msc_gpa_raw"),
        "bsc_qs_rank":      lambda r: r.get("bsc_qs_rank"),
        "msc_qs_rank":      lambda r: r.get("msc_qs_rank"),
        "cp1_conference":   lambda r: ", ".join(
            p.get("venue", "") for p in r.get("publications", [])
            if p.get("pub_type") == "conference"
        ) or "none",
        "cp1_first_author": lambda r: any(
            p.get("author_position") == 1
            for p in r.get("publications", [])
        ),
    }
    fn = mapping.get(field)
    if fn:
        val = fn(extracted)
        return str(val)[:40] if val is not None else "None"
    return "?"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate extraction accuracy against ground truth"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true",
                       help="Run extraction on archive, then evaluate")
    group.add_argument("--results", metavar="FILE",
                       help="Path to previously saved JSON results from test_extraction_standalone.py")
    parser.add_argument("--output", metavar="FILE",
                        help="Save evaluation report JSON to this file")
    args = parser.parse_args()

    if not GROUND_TRUTH_PATH.exists():
        print(f"❌ Ground truth not found: {GROUND_TRUTH_PATH}")
        sys.exit(1)

    gt = load_ground_truth()
    logger.info(f"Ground truth loaded: {len(gt)} annotated candidates")

    if args.run:
        from tests.test_extraction_standalone import load_csvs, discover_pairs, run_all

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("❌ GROQ_API_KEY not set.")
            sys.exit(1)

        dfs = load_csvs()
        # Only run on IDs that appear in ground truth (by name lookup or all if no id match)
        pairs = discover_pairs(ARCHIVE_DIR)
        if not pairs:
            print(f"❌ No files found in {ARCHIVE_DIR}")
            sys.exit(1)

        logger.info(f"Running extraction on {len(pairs)} applicants…")
        results = asyncio.run(run_all(pairs, dfs))

        # Save raw extraction results immediately — this is the expensive part
        # (one LLM call pair per applicant). Do this before report generation so
        # a crash while printing/formatting the report never loses the results.
        raw_dump = PROJECT_ROOT / "data" / "eval_raw_results.json"
        raw_dump.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        logger.info(f"Raw extraction results saved -> {raw_dump}")
    else:
        results_path = Path(args.results)
        if not results_path.exists():
            print(f"❌ Results file not found: {results_path}")
            sys.exit(1)
        results = json.loads(results_path.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(results)} results from {results_path}")

    # Filter out extraction errors
    valid_results = [r for r in results if "error" not in r]
    logger.info(f"{len(valid_results)}/{len(results)} results without extraction errors")

    # Match to ground truth
    pairs = match_to_ground_truth(valid_results, gt)

    # Print report
    print_report(pairs)

    # Optionally save
    if args.output:
        report = []
        for extracted, gt_row in pairs:
            if gt_row is None:
                continue
            eval_r = evaluate_candidate(extracted, gt_row)
            report.append({
                "id": extracted.get("id"),
                "full_name": extracted.get("full_name"),
                "gt_name": gt_row.get("full_name"),
                **eval_r,
            })
        out = Path(args.output)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\n  💾 Report saved to {out}")


if __name__ == "__main__":
    main()
