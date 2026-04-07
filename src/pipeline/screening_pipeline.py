"""
src/pipeline/screening_pipeline.py

FIX: Each call to run_pipeline() uses asyncio.run(), which creates a new event loop.
asyncpg connection pools are bound to a specific event loop, so we must create
a fresh engine/session per asyncio.run() call — never reuse a pool across loops.
"""

import asyncio
import logging
import os
import pandas as pd
from uuid import UUID

# ✅ FIX: Import create_engine factory, NOT the shared SessionLocal
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.db.repositories import applicant_repo, document_repo, publication_repo

from src.ingestion.pdf_reader import PDFReader
from src.preprocessing.cleaner import DocumentCleaner
from src.preprocessing.segmenter import DocumentSegmenter
from src.ai.llm_factory import get_llm_orchestrator
from src.models.extraction_schemas import ExtractedCandidate
from src.extractors.university_extractor import lookup_qs_rank
from src.extractors.publication_extractor import enrich_publication
from src.scoring.normalizer import to_float, normalise_gpa_to_4

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

try:
    df_qs = pd.read_csv(os.path.join(DATA_DIR, "qs_rankings_2025.csv"))
    df_scopus = pd.read_csv(os.path.join(DATA_DIR, "scimagojr_2024_computer_science.csv"))
    df_core = pd.read_csv(os.path.join(DATA_DIR, "core_conferences_2026.csv"))
    df_qs['university_name_clean'] = df_qs['university_name'].str.replace(r'\s*\([^)]*\)', '', regex=True).str.strip()
    qs_names = df_qs['university_name_clean'].tolist()
    logger.info(f"✅ CSV chargés: QS({len(df_qs)}) Scopus({len(df_scopus)}) CORE({len(df_core)})")
except Exception as e:
    logger.error(f"❌ Erreur CSV: {e}")
    df_qs = df_scopus = df_core = None
    qs_names = []


def _make_session_factory():
    """
    ✅ FIX: Create a brand-new engine + session factory tied to the CURRENT event loop.
    Called once per asyncio.run() invocation, so the pool is always loop-compatible.
    """
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:password@postgres:5432/pg_screening"
    )
    engine = create_async_engine(
        database_url,
        # Small pool — this engine is short-lived (one task)
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=60,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine


def _compute_confidence(validated: ExtractedCandidate) -> float:
    scores = [
        0.9 if validated.bsc_uni else 0.1,
        0.9 if validated.bsc_gpa.raw_value else 0.1,
        0.9 if (validated.msc_uni or validated.msc_absent) else 0.1,
        0.8 if validated.publications else 0.3,
    ]
    return round(sum(scores) / len(scores), 3)


def _clean_publications(publications):
    cleaned = []
    for pub in publications:
        if not pub.get('title') or pub.get('title') == "Untitled":
            continue
        if pub.get('year') and not isinstance(pub.get('year'), int):
            pub['year'] = None
        cleaned.append(pub)
    return cleaned


async def run_pipeline_logic(applicant_id: str) -> bool:
    """
    ✅ FIX: Create a fresh session factory for THIS event loop invocation.
    This avoids the asyncpg 'another operation is in progress' error caused
    by reusing a connection pool across different event loops.
    """
    SessionLocal, engine = _make_session_factory()

    try:
        async with SessionLocal() as db:
            app_uuid = UUID(applicant_id)

            app = await applicant_repo.get_applicant(db, app_uuid)
            if not app:
                logger.error(f"❌ Applicant {applicant_id} not found")
                return False

            if app.status == "processed":
                logger.info(f"✅ Applicant {applicant_id} already processed")
                return True

            if app.retry_count >= 5:
                logger.error(f"❌ Applicant {applicant_id} exceeded max retries (5)")
                await applicant_repo.update_applicant_status(db, app_uuid, "failed")
                await db.commit()
                return False

            await applicant_repo.update_applicant_status(db, app_uuid, "processing")
            await db.commit()
            logger.info(f"🟡 [STATUS] {applicant_id} → processing (attempt {app.retry_count + 1})")

        orchestrator = get_llm_orchestrator()

        try:
            logger.info(f"🚀 [PIPELINE START] Applicant: {applicant_id}")

            # ✅ Open a fresh connection for the main work
            async with SessionLocal() as db:
                docs = await document_repo.get_documents_for_applicant(db, app_uuid)
                cv_doc = next((d for d in docs if d.document_type == 'cv'), None)
                tr_doc = next((d for d in docs if d.document_type == 'transcript'), None)

            if not cv_doc or not tr_doc:
                raise FileNotFoundError("CV ou Transcript manquant")

            reader = PDFReader()
            cleaner = DocumentCleaner()
            segmenter = DocumentSegmenter()

            cv_extraction = reader.extract(cv_doc.storage_path)
            tr_extraction = reader.extract(tr_doc.storage_path)

            cv_clean = cleaner.clean(cv_extraction.content)
            tr_clean = cleaner.clean(tr_extraction.content)

            cv_chunks = segmenter.segment(cv_clean)
            tr_chunks = segmenter.segment(tr_clean)

            academic_text = tr_chunks.education or tr_clean
            if len(academic_text.strip()) < 50:
                academic_text = tr_clean

            raw_results = await orchestrator.extract_parallel(
                cv_text=cv_clean,
                tr_text=academic_text,
                candidate_name=cv_doc.original_filename
            )

            if 'publications' in raw_results:
                raw_results['publications'] = _clean_publications(raw_results['publications'])

            validated = ExtractedCandidate(**raw_results)

            bsc_rank = None
            bsc_gpa_norm = None
            if df_qs is not None and validated.bsc_uni:
                bsc_rank = lookup_qs_rank(validated.bsc_uni, df_qs, qs_names)
            if validated.bsc_gpa.raw_value:
                bsc_gpa_norm = normalise_gpa_to_4(validated.bsc_gpa.raw_value, validated.bsc_gpa.scale or 4.0)

            confidence = _compute_confidence(validated)

            metrics_payload = {
                "bsc_uni_name": (validated.bsc_uni or "")[:250] or None,
                "bsc_qs_rank": bsc_rank,
                "bsc_gpa_raw": to_float(validated.bsc_gpa.raw_value),
                "bsc_gpa_scale": to_float(validated.bsc_gpa.scale, 4.0),
                "bsc_gpa_normalised": bsc_gpa_norm,
                "msc_absent": validated.msc_absent,
                "llm_used": True,
                "global_confidence": confidence,
            }

            if not validated.msc_absent and validated.msc_uni:
                msc_rank = None
                msc_gpa_norm = None
                if df_qs is not None:
                    msc_rank = lookup_qs_rank(validated.msc_uni, df_qs, qs_names)
                if validated.msc_gpa and validated.msc_gpa.raw_value:
                    msc_gpa_norm = normalise_gpa_to_4(validated.msc_gpa.raw_value, validated.msc_gpa.scale or 4.0)
                metrics_payload.update({
                    "msc_uni_name": validated.msc_uni[:250],
                    "msc_qs_rank": msc_rank,
                    "msc_gpa_raw": to_float(validated.msc_gpa.raw_value) if validated.msc_gpa else None,
                    "msc_gpa_scale": to_float(validated.msc_gpa.scale, 4.0) if validated.msc_gpa else None,
                    "msc_gpa_normalised": msc_gpa_norm,
                })

            pubs_to_save = []
            async with SessionLocal() as db:
                for idx, p in enumerate(validated.publications):
                    if not p.title or p.title == "Untitled":
                        continue
                    if p.venue:
                        pub_type, scopus_pct, core_rank, core_score = enrich_publication({"venue": p.venue}, df_scopus, df_core)
                    else:
                        pub_type, scopus_pct, core_rank, core_score = "journal", None, None, None

                    pos = to_float(p.author_position, 1)
                    tot = to_float(p.total_authors, 1)
                    contrib = round((tot - pos + 1) / tot, 3) if tot > 0 else 0.5
                    if pos == tot and tot > 1:
                        contrib = 0.85

                    venue_obj = await publication_repo.get_or_create_venue(
                        db, venue_type=pub_type, name=(p.venue or "Unknown")[:250]
                    )

                    pubs_to_save.append({
                        "title": (p.title or "Untitled")[:250],
                        "authors_raw": (p.authors or "Unknown")[:250],
                        "year": p.year,
                        "author_position": int(pos),
                        "total_authors": int(tot),
                        "first_author": int(pos) == 1,
                        "venue_id": venue_obj.id,
                        "pub_type": pub_type,
                        "contribution_score": contrib,
                        "scopus_pct_at_extraction": scopus_pct,
                        "core_score_at_extraction": core_score,
                        "extraction_source": "llm",
                        "position_in_cv": idx + 1,
                    })
                await db.commit()

            # ✅ Final writes in a clean session
            async with SessionLocal() as db:
                await applicant_repo.upsert_extracted_metrics(db, app_uuid, metrics_payload)
                if pubs_to_save:
                    await publication_repo.save_publications_batch(db, app_uuid, pubs_to_save)
                await applicant_repo.reset_retry_count(db, app_uuid)
                await db.commit()

            logger.info(f"✅ [PIPELINE SUCCESS] {applicant_id} — confidence={confidence} pubs={len(pubs_to_save)}")
            return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ [PIPELINE CRASH] {applicant_id}: {error_msg}", exc_info=True)
            async with SessionLocal() as db:
                await applicant_repo.increment_retry_count(db, app_uuid, error_msg[:500])
                await db.commit()
            logger.info(f"🔴 [STATUS] {applicant_id} → error")
            return False

        finally:
            await orchestrator.close()

    finally:
        # ✅ Always dispose the engine to free connections
        await engine.dispose()


def run_pipeline(applicant_id: str) -> bool:
    return asyncio.run(run_pipeline_logic(applicant_id))