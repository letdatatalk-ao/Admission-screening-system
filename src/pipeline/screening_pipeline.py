import asyncio
import logging
import os
import pandas as pd
from uuid import UUID

# Infrastructure DB
from backend.app.db.database import SessionLocal
from backend.app.db.repositories import (
    applicant_repo, document_repo, publication_repo)

# Ingestion & Preprocessing
from src.ingestion.pdf_reader    import PDFReader
from src.preprocessing.cleaner   import DocumentCleaner
from src.preprocessing.segmenter import DocumentSegmenter
from src.ai.llm_service          import LLMOrchestrator
from src.models.extraction_schemas import ExtractedCandidate

# Extractors
from src.extractors.university_extractor  import lookup_qs_rank
from src.extractors.publication_extractor import enrich_publication

# Scoring
from src.scoring.normalizer import to_float, normalise_gpa_to_4

logger = logging.getLogger(__name__)

# ── Référentiels CSV chargés une seule fois au démarrage ─────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

try:
    df_qs     = pd.read_csv(os.path.join(DATA_DIR, "qs_rankings_2025.csv"))
    df_scopus = pd.read_csv(os.path.join(DATA_DIR, "scopus_sjr.csv"))
    df_core   = pd.read_csv(os.path.join(DATA_DIR, "core_rankings.csv"))
    qs_names  = df_qs['university_name'].tolist()
    logger.info("✅ Référentiels CSV chargés.")
except Exception as e:
    logger.error(f"❌ Erreur chargement CSV : {e}")
    df_qs = df_scopus = df_core = None
    qs_names = []


def _compute_confidence(validated: ExtractedCandidate) -> float:
    """Score de confiance global basé sur la présence des champs clés."""
    scores = [
        0.9 if validated.bsc_uni                          else 0.1,
        0.9 if validated.bsc_gpa.raw_value                else 0.1,
        0.9 if (validated.msc_uni or validated.msc_absent) else 0.1,
        0.8 if validated.publications                      else 0.3,
    ]
    return round(sum(scores) / len(scores), 3)


async def run_pipeline_logic(applicant_id: str) -> bool:

    async with SessionLocal() as db:
        app_uuid     = UUID(applicant_id)
        orchestrator = LLMOrchestrator()

        try:
            logger.info(f"🚀 [PIPELINE START] Applicant: {applicant_id}")

            # ── STEP 1 : Récupération documents ──────────────────────────
            docs   = await document_repo.get_documents_for_applicant(db, app_uuid)
            cv_doc = next((d for d in docs if d.document_type == 'cv'),         None)
            tr_doc = next((d for d in docs if d.document_type == 'transcript'), None)

            if not cv_doc or not tr_doc:
                raise FileNotFoundError("Paire CV + Transcript incomplète en base.")

            # ── STEP 2 : Ingestion ────────────────────────────────────────
            reader    = PDFReader()
            cleaner   = DocumentCleaner()
            segmenter = DocumentSegmenter()

            cv_extraction = reader.extract(cv_doc.storage_path)
            tr_extraction = reader.extract(tr_doc.storage_path)

            # Logs OCR pour audit
            for label, extraction in [("CV", cv_extraction), ("TR", tr_extraction)]:
                if extraction.metadata.get("ocr_used"):
                    logger.info(
                        f"{label} OCR activé — "
                        f"avg_chars/page: {extraction.metadata['avg_chars_per_page']}"
                    )
                if not extraction.metadata.get("ocr_available") and extraction.needs_ocr:
                    logger.warning(
                        f"{label} scanné mais Tesseract absent — "
                        f"qualité d'extraction réduite"
                    )

            # Nettoyage
            cv_clean = cleaner.clean(cv_extraction.content)
            tr_clean = cleaner.clean(tr_extraction.content)

            # Segmentation (le transcript va à l'agent académique,
            # le CV aux agents research + identity)
            cv_chunks = segmenter.segment(cv_clean)
            tr_chunks = segmenter.segment(tr_clean)

            # Texte académique = section éducation du transcript
            # + section éducation du CV en fallback si transcript vide
            academic_text = tr_chunks.education or tr_clean
            if len(academic_text.strip()) < 50:
                logger.warning("Transcript education vide — fallback sur texte brut TR")
                academic_text = tr_clean

            # ── STEP 3 : Extraction LLM parallèle ────────────────────────
            # On passe le texte segmenté pour chaque agent :
            # - académique  → transcript (éducation)
            # - research    → CV (publications)
            # - identity    → CV (header)
            raw_results = await orchestrator.extract_parallel(
                cv_text        = cv_clean,
                tr_text        = academic_text,
                candidate_name = cv_doc.original_filename
            )

            logger.info(f"LLM brut: bsc_uni={raw_results.get('bsc_uni')} "
                        f"pubs={len(raw_results.get('publications', []))}")

            # ── STEP 4 : Validation Pydantic ──────────────────────────────
            validated = ExtractedCandidate(**raw_results)

            # ── STEP 5 : Enrichissement BSc ───────────────────────────────
            bsc_rank     = None
            bsc_gpa_norm = None

            if df_qs is not None:
                bsc_rank = lookup_qs_rank(validated.bsc_uni, df_qs, qs_names)

            if validated.bsc_gpa.raw_value:
                bsc_gpa_norm = normalise_gpa_to_4(
                    validated.bsc_gpa.raw_value,
                    validated.bsc_gpa.scale or 4.0
                )

            confidence = _compute_confidence(validated)

            metrics_payload = {
                "bsc_uni_name":       (validated.bsc_uni or "")[:250] or None,
                "bsc_qs_rank":        bsc_rank,
                "bsc_gpa_raw":        to_float(validated.bsc_gpa.raw_value),
                "bsc_gpa_scale":      to_float(validated.bsc_gpa.scale, 4.0),
                "bsc_gpa_normalised": bsc_gpa_norm,
                "msc_absent":         validated.msc_absent,
                "llm_used":           True,
                "global_confidence":  confidence,
                "ocr_used":           (
                    cv_extraction.metadata.get("ocr_used") or
                    tr_extraction.metadata.get("ocr_used")
                ),
            }

            # ── STEP 5b : Enrichissement MSc ─────────────────────────────
            if not validated.msc_absent and validated.msc_uni:
                msc_rank     = None
                msc_gpa_norm = None

                if df_qs is not None:
                    msc_rank = lookup_qs_rank(validated.msc_uni, df_qs, qs_names)

                if validated.msc_gpa and validated.msc_gpa.raw_value:
                    msc_gpa_norm = normalise_gpa_to_4(
                        validated.msc_gpa.raw_value,
                        validated.msc_gpa.scale or 4.0
                    )

                metrics_payload.update({
                    "msc_uni_name":       validated.msc_uni[:250],
                    "msc_qs_rank":        msc_rank,
                    "msc_gpa_raw":        to_float(
                        validated.msc_gpa.raw_value) if validated.msc_gpa else None,
                    "msc_gpa_scale":      to_float(
                        validated.msc_gpa.scale, 4.0) if validated.msc_gpa else None,
                    "msc_gpa_normalised": msc_gpa_norm,
                })

            # ── STEP 6 : Publications ─────────────────────────────────────
            pubs_to_save = []

            for p in validated.publications:
                if p.venue:
                    pub_type, scopus_pct, core_rank, core_score = enrich_publication(
                        {"venue": p.venue}, df_scopus, df_core
                    )
                else:
                    pub_type, scopus_pct, core_rank, core_score = \
                        "journal", None, None, None

                pos    = to_float(p.author_position, 1)
                tot    = to_float(p.total_authors,   1)
                contrib = round((tot - pos + 1) / tot, 3) if tot > 0 else 0.5
                if pos == tot and tot > 1:
                    contrib = 0.85   # bonus dernier auteur senior

                venue_obj = await publication_repo.get_or_create_venue(
                    db,
                    venue_type = pub_type,
                    name       = (p.venue or "Unknown")[:250]
                )

                pubs_to_save.append({
                    "title":                    (p.title   or "Untitled")[:250],
                    "authors_raw":              (p.authors or "Unknown")[:250],
                    "year":                     p.year,
                    "author_position":          int(pos),
                    "total_authors":            int(tot),
                    "first_author":             int(pos) == 1,
                    "venue_id":                 venue_obj.id,
                    "pub_type":                 pub_type,
                    "contribution_score":       contrib,
                    "scopus_pct_at_extraction": scopus_pct,
                    "core_score_at_extraction": core_score,
                    "extraction_source":        "llm_multi_agent",
                })

            # ── STEP 7 : Sauvegarde DB ────────────────────────────────────
            await applicant_repo.update_applicant_status(db, app_uuid, "processing")
            await applicant_repo.upsert_extracted_metrics(db, app_uuid, metrics_payload)

            if pubs_to_save:
                await publication_repo.save_publications_batch(
                    db, app_uuid, pubs_to_save)

            await applicant_repo.update_applicant_status(db, app_uuid, "processed")
            await db.commit()

            logger.info(
                f"✅ [PIPELINE SUCCESS] {applicant_id} — "
                f"confidence={confidence} pubs={len(pubs_to_save)}"
            )
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [PIPELINE CRASH] {applicant_id}: {e}")
            try:
                await applicant_repo.update_applicant_status(db, app_uuid, "error")
                await db.commit()
            except Exception:
                pass
            return False

        finally:
            await orchestrator.close()


def run_pipeline(applicant_id: str) -> bool:
    """Bridge synchrone pour Celery."""
    return asyncio.run(run_pipeline_logic(applicant_id))