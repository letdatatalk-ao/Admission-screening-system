#!/usr/bin/env python3
"""
tests/test_extraction_standalone.py

Test the extraction pipeline directly on archive files.
No Docker, Celery, or PostgreSQL required — only a valid GROQ_API_KEY.

Usage:
    python -m tests.test_extraction_standalone
    python -m tests.test_extraction_standalone --id 002541728
    python -m tests.test_extraction_standalone --limit 3
    python -m tests.test_extraction_standalone --output results.json
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

# Force UTF-8 output — the summary prints a unicode checkmark that crashes
# under Windows' default cp1252 console encoding.
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ARCHIVE_DIR = PROJECT_ROOT / "archive"
DATA_DIR = PROJECT_ROOT / "data"


# ─────────────────────────────────────────────────────────────────────────────
# CSV loading
# ─────────────────────────────────────────────────────────────────────────────

def load_csvs() -> dict:
    dfs: dict = {}
    for key, filename in [
        ("qs",     "qs_rankings_2025.csv"),
        ("scopus", "scimagojr_2024_computer_science.csv"),
        ("core",   "core_conferences_2026.csv"),
    ]:
        path = DATA_DIR / filename
        if path.exists():
            dfs[key] = pd.read_csv(path)
            logger.info(f"  CSV {filename}: {len(dfs[key])} rows")
        else:
            dfs[key] = None
            logger.warning(f"  Missing CSV: {filename}")

    if dfs["qs"] is not None:
        dfs["qs"]["university_name_clean"] = (
            dfs["qs"]["university_name"]
            .str.replace(r"\s*\([^)]*\)", "", regex=True)
            .str.strip()
        )
        dfs["qs_names"] = dfs["qs"]["university_name_clean"].tolist()
    else:
        dfs["qs_names"] = []

    return dfs


# ─────────────────────────────────────────────────────────────────────────────
# Archive file discovery
# ─────────────────────────────────────────────────────────────────────────────

_SUPPORTED = {".pdf", ".docx"}

def _extract_id_and_role(stem: str):
    """
    Parse archive file stems into (applicant_id, role).
    Handles two naming conventions:
      '{ID} CV'  /  '{ID} T'    (most common)
      'CV {ID}'  /  'T {ID}'    (some files)
    Returns (id_str, 'cv'|'transcript') or (None, None).
    """
    stem = stem.strip()
    m = re.match(r"^(\d+)\s+(CV|T)$", stem, re.IGNORECASE)
    if m:
        return m.group(1), ("cv" if m.group(2).upper() == "CV" else "transcript")
    m = re.match(r"^(CV|T)\s+(\d+)$", stem, re.IGNORECASE)
    if m:
        return m.group(2), ("cv" if m.group(1).upper() == "CV" else "transcript")
    return None, None


def discover_pairs(archive_dir: Path, target_id: str = None, limit: int = None):
    """
    Scan archive/ and return list of (cv_path, transcript_path, applicant_id).
    transcript_path may be None if only a CV exists.
    """
    cv_map: dict[str, Path] = {}
    tr_map: dict[str, Path] = {}

    for f in archive_dir.iterdir():
        if f.suffix.lower() not in _SUPPORTED:
            continue
        aid, role = _extract_id_and_role(f.stem)
        if aid is None:
            continue
        if role == "cv":
            cv_map[aid] = f
        elif role == "transcript":
            tr_map[aid] = f

    pairs = []
    for aid in sorted(cv_map):
        if target_id and aid != target_id:
            continue
        pairs.append((cv_map[aid], tr_map.get(aid), aid))

    # Include transcripts with no CV (should not happen, but log them)
    for aid in tr_map:
        if aid not in cv_map:
            logger.warning(f"  Transcript without CV: {aid}")

    if limit:
        pairs = pairs[:limit]

    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# Document reading
# ─────────────────────────────────────────────────────────────────────────────

def read_document(path: Path) -> str:
    if not path or not path.exists():
        return ""
    try:
        # Magic bytes over extension — some archive files are mislabelled
        # (e.g. a PDF saved with a .docx name). See screening_pipeline.py.
        with open(path, "rb") as fh:
            magic = fh.read(4)
        if magic == b"%PDF":
            from src.ingestion.pdf_reader import PDFReader
            return PDFReader().extract(str(path)).content
        if path.suffix.lower() == ".docx":
            from src.ingestion.docx_reader import DocxReader
            return DocxReader().extract(str(path)).content
        from src.ingestion.pdf_reader import PDFReader
        return PDFReader().extract(str(path)).content
    except Exception as e:
        logger.error(f"  Failed to read {path.name}: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Single applicant extraction
# ─────────────────────────────────────────────────────────────────────────────

def _build_orchestrator(provider: str):
    if provider == "qwen":
        from src.ai.qwen_service import QwenOrchestrator
        return QwenOrchestrator()
    from src.ai.groq_service import GroqOrchestrator
    return GroqOrchestrator()


async def extract_one(aid: str, cv_path: Path, tr_path: Path, dfs: dict, provider: str = "groq") -> dict:
    from src.preprocessing.cleaner import DocumentCleaner
    from src.preprocessing.segmenter import DocumentSegmenter
    from src.extractors.university_extractor import lookup_qs_rank
    from src.extractors.publication_extractor import enrich_publication
    from src.scoring.normalizer import normalise_gpa_to_4
    from src.models.extraction_schemas import ExtractedCandidate

    cleaner = DocumentCleaner()
    segmenter = DocumentSegmenter()

    logger.info(f"\n{'─'*60}")
    logger.info(f"[{aid}] CV={cv_path.name if cv_path else 'MISSING'}  "
                f"T={tr_path.name if tr_path else 'MISSING'}")

    cv_text = cleaner.clean(read_document(cv_path)) if cv_path else ""
    tr_raw = read_document(tr_path) if tr_path else ""
    tr_clean = cleaner.clean(tr_raw)

    tr_chunks = segmenter.segment(tr_clean)
    academic_text = tr_chunks.education or tr_clean
    if len(academic_text.strip()) < 100:
        academic_text = tr_clean

    if not cv_text.strip() and not academic_text.strip():
        logger.error(f"  [{aid}] No text extracted — skipping")
        return {"id": aid, "error": "no_text"}

    logger.info(f"  [{aid}] CV={len(cv_text):,}ch  TR={len(academic_text):,}ch")

    orchestrator = _build_orchestrator(provider)
    try:
        raw = await orchestrator.extract_parallel(
            cv_text=cv_text,
            tr_text=academic_text,
            candidate_name=aid,
        )
    except Exception as e:
        logger.error(f"  [{aid}] LLM extraction failed: {e}")
        return {"id": aid, "error": str(e)}
    finally:
        await orchestrator.close()

    try:
        validated = ExtractedCandidate(**raw)
    except Exception as e:
        logger.warning(f"  [{aid}] Validation error: {e} — using raw values")
        validated = None

    if validated is None:
        return {"id": aid, "error": "validation_failed", "raw": raw}

    # QS rank lookups
    bsc_rank = (
        lookup_qs_rank(validated.bsc_uni, dfs["qs"], dfs["qs_names"])
        if validated.bsc_uni and dfs["qs"] is not None else None
    )
    msc_rank = (
        lookup_qs_rank(validated.msc_uni, dfs["qs"], dfs["qs_names"])
        if validated.msc_uni and dfs["qs"] is not None else None
    )

    # GPA normalisation
    bsc_gpa_norm = None
    if validated.bsc_gpa.raw_value:
        bsc_gpa_norm = normalise_gpa_to_4(
            validated.bsc_gpa.raw_value, validated.bsc_gpa.scale
        )

    msc_gpa_norm = None
    if validated.msc_gpa and validated.msc_gpa.raw_value:
        msc_gpa_norm = normalise_gpa_to_4(
            validated.msc_gpa.raw_value, validated.msc_gpa.scale
        )

    # Publication enrichment
    enriched_pubs = []
    for p in validated.publications:
        if p.venue:
            pub_type, scopus_pct, rank_or_quartile, core_score = enrich_publication(
                {"venue": p.venue}, dfs["scopus"], dfs["core"]
            )
        else:
            pub_type, scopus_pct, rank_or_quartile, core_score = "journal", None, None, None

        enriched_pubs.append({
            "title": p.title,
            "year": p.year,
            "venue": p.venue,
            "pub_type": pub_type,
            "scopus_pct": scopus_pct,
            "rank_or_quartile": rank_or_quartile,
            "core_score": core_score,
            "author_position": p.author_position,
            "total_authors": p.total_authors,
        })

    result = {
        "id": aid,
        "full_name": validated.full_name,
        "email": validated.email,
        "bsc_uni": validated.bsc_uni,
        "bsc_qs_rank": bsc_rank,
        "bsc_gpa_raw": validated.bsc_gpa.raw_value,
        "bsc_gpa_scale": validated.bsc_gpa.scale,
        "bsc_gpa_norm": bsc_gpa_norm,
        "msc_uni": validated.msc_uni,
        "msc_absent": validated.msc_absent,
        "msc_qs_rank": msc_rank,
        "msc_gpa_raw": validated.msc_gpa.raw_value if validated.msc_gpa else None,
        "msc_gpa_scale": validated.msc_gpa.scale if validated.msc_gpa else None,
        "msc_gpa_norm": msc_gpa_norm,
        "publications": enriched_pubs,
        "pub_count": len(enriched_pubs),
    }

    _log_result(aid, result)
    return result


def _log_result(aid: str, r: dict) -> None:
    bsc_gpa_str = (
        f"{r['bsc_gpa_raw']}/{r['bsc_gpa_scale']} → {r['bsc_gpa_norm']:.3f}/4.0"
        if r["bsc_gpa_raw"] else "N/A"
    )
    msc_gpa_str = (
        f"{r['msc_gpa_raw']}/{r['msc_gpa_scale']} → {r['msc_gpa_norm']:.3f}/4.0"
        if r["msc_gpa_raw"] else "N/A"
    )
    logger.info(
        f"  [{aid}] BSc: {r['bsc_uni'] or 'NOT FOUND'!r} | "
        f"GPA={bsc_gpa_str} | QS#{r['bsc_qs_rank']}"
    )
    logger.info(
        f"  [{aid}] MSc: {(r['msc_uni'] or ('absent' if r['msc_absent'] else 'NOT FOUND'))!r} | "
        f"GPA={msc_gpa_str} | QS#{r['msc_qs_rank']}"
    )
    logger.info(f"  [{aid}] Publications: {r['pub_count']}")
    for pub in r["publications"]:
        q = pub["rank_or_quartile"] or pub["core_score"] or "unranked"
        logger.info(
            f"    [{(pub['pub_type'] or '?')[:1].upper()}] {(pub['title'] or '?')[:70]}  "
            f"({pub['year']})  venue={q}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def run_all(pairs: list, dfs: dict, provider: str = "groq") -> list:
    results = []
    for cv_path, tr_path, aid in pairs:
        result = await extract_one(aid, cv_path, tr_path, dfs, provider=provider)
        results.append(result)
    return results


def print_summary(results: list) -> None:
    ok = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    print(f"\n{'='*70}")
    print(f"EXTRACTION SUMMARY — {len(results)} applicant(s)")
    print(f"{'='*70}")

    for r in ok:
        bsc_gpa = f"{r['bsc_gpa_norm']:.3f}" if r["bsc_gpa_norm"] else "  N/A"
        msc_gpa = f"{r['msc_gpa_norm']:.3f}" if r["msc_gpa_norm"] else "  N/A"
        msc_uni = r["msc_uni"] or ("(absent)" if r["msc_absent"] else "NOT FOUND")
        print(
            f"  {r['id']:<12} {(r.get('full_name') or '?'):<30} "
            f"BSc_GPA={bsc_gpa}  MSc_GPA={msc_gpa}  pubs={r['pub_count']:<3} "
            f"msc={msc_uni[:30]}"
        )

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors:
            print(f"    {e['id']}: {e.get('error')}")

    n_bsc  = sum(1 for r in ok if r["bsc_uni"])
    n_msc  = sum(1 for r in ok if r["msc_uni"] or r["msc_absent"])
    n_bgpa = sum(1 for r in ok if r["bsc_gpa_raw"])
    n_mgpa = sum(1 for r in ok if r["msc_gpa_raw"])
    total  = len(ok) or 1

    print(f"\n  Field extraction rates (out of {len(ok)} processed):")
    print(f"    BSc university:   {n_bsc}/{len(ok)}  ({100*n_bsc//total}%)")
    print(f"    MSc university:   {n_msc}/{len(ok)}  ({100*n_msc//total}%)")
    print(f"    BSc GPA:          {n_bgpa}/{len(ok)}  ({100*n_bgpa//total}%)")
    print(f"    MSc GPA:          {n_mgpa}/{len(ok)}  ({100*n_mgpa//total}%)")
    print(f"\n  ✅ Success: {len(ok)}/{len(results)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test extraction pipeline on archive files (no Docker needed)"
    )
    parser.add_argument("--id", metavar="APPLICANT_ID",
                        help="Process only this applicant ID (e.g. 002541728)")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Process at most N applicants")
    parser.add_argument("--output", metavar="FILE",
                        help="Save JSON results to this file")
    parser.add_argument("--provider", choices=["groq", "qwen"], default="groq",
                        help="LLM provider to test against (default: groq)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.provider == "qwen":
        if not (os.getenv("SCALEWAY_API_KEY") and os.getenv("SCALEWAY_BASE_URL")):
            print("❌ SCALEWAY_API_KEY / SCALEWAY_BASE_URL not set.\n"
                  "   Add them to .env in project root.")
            sys.exit(1)
    else:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("❌ GROQ_API_KEY not set.\n"
                  "   Export it:  export GROQ_API_KEY=gsk_...\n"
                  "   Or add it to .env in project root.")
            sys.exit(1)

    logger.info(f"Loading reference CSVs from {DATA_DIR}")
    dfs = load_csvs()

    pairs = discover_pairs(ARCHIVE_DIR, target_id=args.id, limit=args.limit)
    if not pairs:
        logger.error(f"No applicant files found in {ARCHIVE_DIR}")
        sys.exit(1)

    logger.info(f"Found {len(pairs)} applicant(s) to process (provider={args.provider})\n")

    results = asyncio.run(run_all(pairs, dfs, provider=args.provider))
    print_summary(results)

    if args.output:
        out = Path(args.output)
        out.write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8"
        )
        print(f"\n  💾 Results saved to {out}")


if __name__ == "__main__":
    main()
