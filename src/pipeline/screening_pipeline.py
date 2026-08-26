"""
src/pipeline/screening_pipeline.py
"""

import asyncio
import logging
import os
import re
import time
import unicodedata
import pandas as pd
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.db.repositories import (
    applicant_repo,
    document_repo,
    publication_repo,
)

from src.ingestion.pdf_reader import PDFReader
from src.ingestion.docx_reader import DocxReader
from src.ingestion import vlm_ocr, docling_reader
from src.preprocessing.cleaner import DocumentCleaner
from src.preprocessing.segmenter import DocumentSegmenter
from src.ai.llm_factory import get_llm_orchestrator
from src.models.extraction_schemas import ExtractedCandidate
from src.extractors.university_extractor import lookup_qs_rank
from src.extractors.publication_extractor import enrich_publication
from src.extractors.doi_verifier import verify_dois
from src.scoring.normalizer import to_float, normalise_gpa_to_4
from src.preprocessing.sanitizer import detect_document_language
from src.monitoring.metrics import (
    PIPELINE_RUNS, PIPELINE_DURATION, ACTIVE_PIPELINES,
    CONFIDENCE_SCORE, OCR_QUALITY, REVIEW_REASONS, DOI_VERIFICATIONS,
)

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

try:
    df_qs     = pd.read_csv(os.path.join(DATA_DIR, "qs_rankings_2025.csv"))
    df_scopus = pd.read_csv(os.path.join(DATA_DIR, "scimagojr_2024_computer_science.csv"))
    df_core   = pd.read_csv(os.path.join(DATA_DIR, "core_conferences_2026.csv"))
    df_qs["university_name_clean"] = (
        df_qs["university_name"].str.replace(r"\s*\([^)]*\)", "", regex=True).str.strip()
    )
    qs_names = df_qs["university_name_clean"].tolist()
    logger.info(f"✅ CSV loaded: QS({len(df_qs)}) Scopus({len(df_scopus)}) CORE({len(df_core)})")
except Exception as e:
    logger.error(f"❌ CSV load error: {e}")
    df_qs = df_scopus = df_core = None
    qs_names = []


# ── DB engine singleton — loop-ID-aware (safe under Celery prefork) ───────────
# asyncio.run() in each Celery task creates a new event loop, which invalidates
# AsyncEngine / aioredis connections bound to a previous loop.  We track the
# id() of the running loop and recreate the engine whenever it changes.
_ENGINE: Optional[AsyncEngine] = None
_SESSION_FACTORY: Optional[async_sessionmaker] = None
_DB_LOOP_ID: Optional[int] = None


def _get_db() -> async_sessionmaker:
    global _ENGINE, _SESSION_FACTORY, _DB_LOOP_ID
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    current_id = id(loop)
    if _SESSION_FACTORY is None or _DB_LOOP_ID != current_id:
        if _DB_LOOP_ID is not None and _DB_LOOP_ID != current_id:
            logger.warning(
                f"Event loop changed ({_DB_LOOP_ID} → {current_id}) — recreating DB engine"
            )
        url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:password@postgres:5432/pg_screening",
        )
        _ENGINE = create_async_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        _SESSION_FACTORY = async_sessionmaker(
            _ENGINE, class_=AsyncSession, expire_on_commit=False
        )
        _DB_LOOP_ID = current_id
        logger.info(f"✅ DB engine initialised for loop {current_id}")
    return _SESSION_FACTORY


# ── Distributed pipeline lock (Redis SET NX EX) ───────────────────────────────
_REDIS_URL     = os.getenv("REDIS_URL", "redis://redis:6379/0")
_LOCK_TTL      = 600        # seconds — generous; pipeline completes in < 3 min
_LOCK_PREFIX   = "pipeline:lock:"
_STORAGE_ROOT  = os.path.realpath(
    os.getenv("STORAGE_ROOT", os.path.join(os.path.dirname(__file__), "..", "..", "storage"))
)

_redis_client: Optional[aioredis.Redis] = None
_REDIS_LOOP_ID: Optional[int] = None


def _get_redis() -> aioredis.Redis:
    global _redis_client, _REDIS_LOOP_ID
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    current_id = id(loop)
    if _redis_client is None or _REDIS_LOOP_ID != current_id:
        if _REDIS_LOOP_ID is not None and _REDIS_LOOP_ID != current_id:
            logger.debug("Event loop changed — recreating Redis client")
        _redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
        _REDIS_LOOP_ID = current_id
    return _redis_client


async def _acquire_lock(applicant_id: str) -> bool:
    """
    Acquire a per-applicant mutex in Redis (SET NX EX).
    Returns True if the lock was acquired (safe to proceed).
    Fails open on Redis errors so a Redis outage never blocks processing.
    """
    try:
        r = _get_redis()
        acquired = await r.set(_LOCK_PREFIX + applicant_id, "1", nx=True, ex=_LOCK_TTL)
        if not acquired:
            logger.warning(
                f"⚠️ [{applicant_id}] Lock already held by another worker — skipping"
            )
        return bool(acquired)
    except Exception as e:
        logger.warning(f"Redis lock unavailable ({e}) — proceeding without lock")
        return True   # fail open


async def _release_lock(applicant_id: str) -> None:
    try:
        r = _get_redis()
        await r.delete(_LOCK_PREFIX + applicant_id)
    except Exception:
        pass   # best-effort; TTL will expire it anyway


# ── Path traversal guard ──────────────────────────────────────────────────────

def _validate_storage_path(path: str) -> str:
    """
    Resolve the storage path and verify it is inside STORAGE_ROOT.
    Raises ValueError on path traversal attempts.
    """
    resolved = os.path.realpath(path)
    if not resolved.startswith(_STORAGE_ROOT + os.sep) and resolved != _STORAGE_ROOT:
        raise ValueError(
            f"Security: storage path {path!r} resolves to {resolved!r} "
            f"which is outside the allowed storage root {_STORAGE_ROOT!r}"
        )
    return resolved


# ── Fix 3: blocking I/O runs in a thread pool, not the event loop ─────────────

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp"})


def _read_image_file_sync(path: str) -> tuple[str, float, str]:
    """
    Extract text from a standalone image file (phone photo, scanner output, etc.)
    Cascade: Groq VLM vision → Tesseract fallback.
    """
    with open(path, "rb") as fh:
        img_bytes = fh.read()

    vlm_text = vlm_ocr.extract_pages_vlm([img_bytes])
    if vlm_text:
        return vlm_text, 0.82, "image_vlm"

    # Tesseract fallback
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img, lang="eng")
        if text.strip():
            return text, 0.55, "image_tesseract"
    except Exception as e:
        logger.warning(f"Tesseract fallback failed for image {path}: {e}")

    return "[OCR_UNAVAILABLE]", 0.0, "image"


def _read_document_rich_sync(path: str) -> tuple[str, float, str]:
    """
    Synchronous worker — called via asyncio.to_thread().
    Returns (content, ocr_quality 0–1, file_type string).
    Validates path against STORAGE_ROOT before opening.

    Extraction cascade:
      1. Standalone image files → VLM vision OCR (Groq) → Tesseract
      2. DOCX → Docling (if available) → python-docx
      3. Native PDF → Docling (if available) → PyMuPDF
      4. Scanned PDF → PyMuPDF+Tesseract → VLM vision OCR if quality < 0.50
    """
    path = _validate_storage_path(path)

    # ── Standalone image files ────────────────────────────────────────────────
    _, suffix = os.path.splitext(path)
    if suffix.lower() in _IMAGE_EXTENSIONS:
        return _read_image_file_sync(path)

    # ── DOCX ─────────────────────────────────────────────────────────────────
    with open(path, "rb") as fh:
        magic = fh.read(5)

    # Magic bytes are authoritative over the file extension — mislabelled
    # uploads happen in practice (e.g. a PDF exported/renamed with a .docx
    # extension). Only route to the DOCX reader when the extension says .docx
    # AND the content isn't unambiguously a PDF.
    if magic[:4] == b"%PDF":
        if path.lower().endswith(".docx"):
            logger.warning(
                f"⚠️ {path}: filename ends in .docx but content is PDF (magic=%PDF) — "
                "treating as PDF"
            )
    elif magic[:2] == b"PK" or path.lower().endswith(".docx"):
        if docling_reader.is_available():
            result = docling_reader.extract(path, do_ocr=False)
            if result:
                return result  # (markdown, quality, file_type)
        doc_ext = DocxReader().extract(path)
        return doc_ext.content, 1.0, "docx"

    # ── PDF ───────────────────────────────────────────────────────────────────
    pdf_ext = PDFReader().extract(path)

    if pdf_ext.doc_type == "native":
        # Native (text-based) PDF — try Docling first for better table/layout parsing
        if docling_reader.is_available():
            result = docling_reader.extract(path, do_ocr=False)
            if result:
                return result
        avg = pdf_ext.metadata.get("avg_chars_per_page", 0)
        quality = min(1.0, round(avg / 800.0, 3))
        return pdf_ext.content, quality, "native_pdf"

    # Scanned PDF — Tesseract ran already (page_images populated)
    tesseract_ok = pdf_ext.metadata.get("ocr_available", False)
    tesseract_quality = 0.65 if tesseract_ok else 0.0

    # Upgrade to VLM OCR when Tesseract quality is poor or OCR was unavailable
    if tesseract_quality < 0.50 and pdf_ext.page_images:
        vlm_text = vlm_ocr.extract_pages_vlm(pdf_ext.page_images)
        if vlm_text:
            logger.info(
                f"VLM OCR replaced Tesseract for {path} "
                f"(tesseract_quality={tesseract_quality})"
            )
            return vlm_text, 0.85, "vlm_ocr_pdf"

    return pdf_ext.content, tesseract_quality, "scanned_pdf"


async def _read_document_rich(path: str) -> tuple[str, float, str]:
    """Async wrapper — offloads PDF/DOCX I/O to a thread."""
    return await asyncio.to_thread(_read_document_rich_sync, path)


# ── Fix 2: GPA cross-validation ───────────────────────────────────────────────

def _extract_gpa_patterns(text: str) -> list[tuple[float, float]]:
    """Find all X/Y GPA patterns in text. Returns [(raw, scale)]."""
    results = []
    pat = re.compile(
        r"(?:cgpa|gpa|cumulative|overall|average|moyenne)?[\s:=]*"
        r"([0-9]{1,2}\.?[0-9]{0,3})\s*/\s*([0-9]{1,3}\.?[0-9]{0,2})",
        re.IGNORECASE,
    )
    known = [4.0, 5.0, 10.0, 20.0, 100.0]
    for m in pat.finditer(text):
        try:
            raw   = float(m.group(1))
            scale = float(m.group(2))
            if not (0 < raw <= scale <= 100 and raw >= 1.0):
                continue
            closest = min(known, key=lambda x: abs(x - scale))
            if abs(closest - scale) <= 0.5:
                results.append((raw, closest))
        except ValueError:
            continue
    return results


def _check_gpa_cross_validation(
    llm_gpa_raw: Optional[float],
    llm_gpa_scale: Optional[float],
    tr_text: str,
) -> Optional[str]:
    """
    Compares the LLM-extracted GPA against GPA patterns in the raw transcript.
    Returns a warning string when discrepancy > 10 % of scale, else None.
    """
    if not llm_gpa_raw or not tr_text:
        return None

    # Cumulative GPA usually printed at the end of the transcript
    tr_gpas = _extract_gpa_patterns(tr_text[-3000:]) or _extract_gpa_patterns(tr_text)
    if not tr_gpas:
        return None

    llm_scale = llm_gpa_scale or 4.0
    llm_norm  = llm_gpa_raw / llm_scale

    same_scale = [(r, s) for r, s in tr_gpas if abs(s - llm_scale) < 0.5]
    candidates = same_scale if same_scale else tr_gpas
    tr_raw, tr_scale = candidates[-1]   # last = cumulative
    tr_norm = tr_raw / tr_scale

    if abs(llm_norm - tr_norm) > 0.10:
        return (
            f"GPA mismatch: LLM extracted {llm_gpa_raw:.2f}/{llm_scale:.1f} "
            f"but transcript shows {tr_raw:.2f}/{tr_scale:.1f}"
        )
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_name_hint(filename: str) -> str:
    name = re.sub(r"\.(pdf|docx?|doc)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"\b\d{4,}\b", "", name)
    name = re.sub(
        r"\b(cv|resume|curriculum[\s_]?vitae|application)\b",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"[_\-\.]+", " ", name).strip()
    tokens = [t for t in name.split() if len(t) >= 3]
    return name if len(tokens) >= 2 else ""


def _detect_misfile(cv_text: str, tr_text: str, extracted_name: str) -> bool:
    if not extracted_name or not tr_text:
        return False

    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s.lower())
        return "".join(c for c in s if not unicodedata.combining(c))

    tr_window  = _norm(tr_text[:5000])
    significant = [p for p in extracted_name.split() if len(_norm(p)) >= 4]
    if not significant:
        return False

    found = sum(1 for p in significant if _norm(p) in tr_window)
    return found < max(1, len(significant) // 2)


def _compute_confidence(validated: ExtractedCandidate) -> float:
    bsc_uni_ok  = 0.20 if validated.bsc_uni else 0.0
    bsc_gpa_ok  = 0.15 if validated.bsc_gpa.raw_value else 0.0
    msc_ok      = 0.25 if (validated.msc_uni or validated.msc_absent) else 0.0

    # Publications: bonus for published work, neutral (not zero) when absent.
    # Early-career applicants straight from BSc/MSc often have no publications —
    # penalising them with 0.0 here would incorrectly flag them for human review.
    published = [p for p in validated.publications if not p.under_review]
    pub_ok    = 0.20 if published else 0.10   # 0.10 = neutral baseline

    identity_ok = 0.20 if (validated.full_name and validated.email) else (
                  0.10 if validated.full_name else 0.0)
    return round(bsc_uni_ok + bsc_gpa_ok + msc_ok + pub_ok + identity_ok, 3)


def _clean_publications(publications: list) -> list:
    cleaned = []
    for pub in publications:
        if not pub.get("title") or pub.get("title") == "Untitled":
            continue
        if pub.get("year") and not isinstance(pub.get("year"), int):
            pub["year"] = None
        cleaned.append(pub)
    return cleaned


# ── Supervisor matching ───────────────────────────────────────────────────────

def _compute_keyword_match(
    interests: list[str],
    areas: list[str],
) -> tuple[float, list[str]]:
    """
    Jaccard similarity between applicant research interests and supervisor areas.
    Tokenizes on whitespace and punctuation; ignores tokens shorter than 3 chars.
    Returns (score 0–1, list of matched keywords).
    """
    if not interests or not areas:
        return 0.0, []

    def _tokenize(phrases: list[str]) -> set[str]:
        tokens: set[str] = set()
        for phrase in phrases:
            for tok in re.split(r"[\s,;/\-]+", phrase.lower()):
                tok = tok.strip()
                if len(tok) >= 3:
                    tokens.add(tok)
        return tokens

    a_set = _tokenize(interests)
    s_set = _tokenize(areas)
    if not a_set or not s_set:
        return 0.0, []

    intersection = a_set & s_set
    union        = a_set | s_set
    score        = len(intersection) / len(union)
    return round(score, 3), sorted(intersection)


async def _match_supervisors(
    SessionLocal: async_sessionmaker,
    applicant_id: UUID,
    interests: list[str],
) -> None:
    """Compute and persist top-5 supervisor matches for this applicant."""
    from backend.app.db.repositories.supervisor_repo import (
        get_all_supervisors,
        upsert_supervisor_matches,
    )
    async with SessionLocal() as db:
        supervisors = await get_all_supervisors(db, accepting_only=True)
        matches = []
        for sup in supervisors:
            score, keywords = _compute_keyword_match(interests, sup.research_areas or [])
            if score > 0:
                matches.append({
                    "supervisor_id":    sup.id,
                    "match_score":      score,
                    "matched_keywords": keywords,
                })
        if matches:
            matches.sort(key=lambda x: x["match_score"], reverse=True)
            await upsert_supervisor_matches(db, applicant_id, matches[:5])
            await db.commit()
            logger.info(
                f"✅ [{applicant_id}] Supervisor matching: "
                f"{len(matches)} candidate(s), top score={matches[0]['match_score']}"
            )


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline_logic(applicant_id: str) -> bool:
    SessionLocal = _get_db()   # singleton — no engine.dispose() per call

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
            logger.error(f"❌ Applicant {applicant_id} exceeded max retries")
            await applicant_repo.update_applicant_status(db, app_uuid, "failed")
            await db.commit()
            return False

        await applicant_repo.update_applicant_status(db, app_uuid, "processing")
        await db.commit()
        logger.info(f"🟡 [STATUS] {applicant_id} → processing (attempt {app.retry_count + 1})")

    # ── Distributed lock: prevent double-processing by concurrent workers ────
    if not await _acquire_lock(applicant_id):
        PIPELINE_RUNS.labels(status="lock_denied").inc()
        return False   # another worker already has this applicant

    _pipeline_start = time.monotonic()
    ACTIVE_PIPELINES.inc()

    orchestrator = get_llm_orchestrator()

    try:
        logger.info(f"🚀 [PIPELINE START] Applicant: {applicant_id}")

        async with SessionLocal() as db:
            docs   = await document_repo.get_documents_for_applicant(db, app_uuid)
            cv_doc = next((d for d in docs if d.document_type == "cv"), None)
            tr_doc = next((d for d in docs if d.document_type == "transcript"), None)

        if not cv_doc:
            raise FileNotFoundError("CV missing — cannot process without CV")

        if not tr_doc:
            logger.warning(f"⚠️ [{applicant_id}] Transcript absent — CV-only mode")

        cleaner   = DocumentCleaner()
        segmenter = DocumentSegmenter()
        review_reasons: list[str] = []

        # ── Fix 3: non-blocking document reads ───────────────────────────────
        cv_raw, cv_quality, cv_file_type = await _read_document_rich(cv_doc.storage_path)

        if "[OCR_UNAVAILABLE]" in cv_raw:
            raise ValueError(
                "CV is a scanned image-only PDF and OCR is not available. "
                "Please upload a text-based PDF or install Tesseract."
            )

        cv_clean = cleaner.clean(cv_raw)

        if len(cv_clean.strip()) < 100:
            raise ValueError(
                "CV document contains insufficient text after extraction — "
                "possibly encrypted, password-protected, or corrupt."
            )

        cv_chunks = segmenter.segment(cv_clean)

        tr_clean      = ""
        academic_text = ""
        tr_raw_text   = ""
        tr_quality    = None
        tr_file_type  = None

        if tr_doc:
            tr_raw, tr_quality, tr_file_type = await _read_document_rich(tr_doc.storage_path)
            tr_raw_text = tr_raw  # kept for GPA cross-validation below
            if "[OCR_UNAVAILABLE]" not in tr_raw:
                tr_clean      = cleaner.clean(tr_raw)
                tr_chunks     = segmenter.segment(tr_clean)
                academic_text = tr_chunks.education or tr_clean
                if len(academic_text.strip()) < 100:
                    academic_text = tr_clean
            else:
                logger.warning(f"⚠️ [{applicant_id}] Transcript OCR unavailable — CV-only mode")
                review_reasons.append("transcript_ocr_unavailable")
                tr_quality   = 0.0
                tr_file_type = "scanned_pdf"

        # ── Write OCR quality scores (Fix 17 from previous round) ────────────
        async with SessionLocal() as db:
            await document_repo.update_ocr_quality(db, cv_doc.id, cv_quality, cv_file_type)
            if tr_doc and tr_quality is not None:
                await document_repo.update_ocr_quality(db, tr_doc.id, tr_quality, tr_file_type)
            await db.commit()

        OCR_QUALITY.labels(file_type=cv_file_type).observe(cv_quality)
        if tr_doc and tr_quality is not None and tr_file_type:
            OCR_QUALITY.labels(file_type=tr_file_type).observe(tr_quality)

        # ── Duplicate file check ──────────────────────────────────────────────
        if cv_doc.file_hash:
            async with SessionLocal() as db:
                dup = await document_repo.find_duplicate_document(
                    db, cv_doc.file_hash, app_uuid
                )
            if dup:
                logger.warning(
                    f"⚠️ [{applicant_id}] CV hash matches applicant {dup} — "
                    "possible duplicate submission"
                )
                review_reasons.append("duplicate_cv_file")

        # ── Language detection (multilingual prompts) ─────────────────────────
        cv_language = detect_document_language(cv_clean)
        if cv_language != "english":
            logger.info(f"🌐 [{applicant_id}] Detected CV language: {cv_language}")

        # ── LLM extraction ────────────────────────────────────────────────────
        candidate_name_hint = _extract_name_hint(cv_doc.original_filename)

        raw_results = await orchestrator.extract_parallel(
            cv_text=cv_clean,
            tr_text=academic_text,
            candidate_name=candidate_name_hint,
            cv_education=cv_chunks.education,
            cv_publications=cv_chunks.publications,
            cv_experience=cv_chunks.experience,
            cv_language=cv_language,
        )

        if "publications" in raw_results:
            raw_results["publications"] = _clean_publications(raw_results["publications"])

        validated = ExtractedCandidate(**raw_results)

        # ── Fix 2: GPA cross-validation ───────────────────────────────────────
        if tr_raw_text and validated.msc_gpa and validated.msc_gpa.raw_value:
            gpa_warn = _check_gpa_cross_validation(
                validated.msc_gpa.raw_value,
                validated.msc_gpa.scale,
                tr_raw_text,   # use raw transcript (before cleaning) for regex matching
            )
            if gpa_warn:
                logger.warning(f"⚠️ [{applicant_id}] {gpa_warn}")
                review_reasons.append(f"gpa_mismatch:{gpa_warn}")

        # ── QS lookups ────────────────────────────────────────────────────────
        bsc_rank = msc_rank = phd_rank = None
        bsc_gpa_norm = msc_gpa_norm = None

        if df_qs is not None:
            if validated.bsc_uni:
                bsc_rank = lookup_qs_rank(validated.bsc_uni, df_qs, qs_names)
            if validated.msc_uni:
                msc_rank = lookup_qs_rank(validated.msc_uni, df_qs, qs_names)
            if validated.phd_uni:
                phd_rank = lookup_qs_rank(validated.phd_uni, df_qs, qs_names)

        # Flag unranked universities for human review so the committee can verify
        # whether the institution is strong despite being absent from QS top-1500.
        from src.scoring.config import get_scoring_config as _get_scoring_cfg
        if _get_scoring_cfg().get("academic", {}).get("qs_flag_unranked_for_review", True):
            if validated.bsc_uni and bsc_rank is None:
                review_reasons.append(f"unranked_bsc_university:{validated.bsc_uni[:60]}")
            if validated.msc_uni and msc_rank is None:
                review_reasons.append(f"unranked_msc_university:{validated.msc_uni[:60]}")

        if validated.bsc_gpa.raw_value:
            bsc_gpa_norm = normalise_gpa_to_4(
                validated.bsc_gpa.raw_value,
                validated.bsc_gpa.scale or 4.0,
                country=validated.bsc_country,
            )

        confidence = _compute_confidence(validated)

        # ── Misfile detection ─────────────────────────────────────────────────
        misfile_detected = False
        if tr_doc and tr_clean and validated.full_name:
            if _detect_misfile(cv_clean, tr_clean, validated.full_name):
                misfile_detected = True
                review_reasons.append("possible_misfile")
                logger.warning(
                    f"⚠️ [{applicant_id}] Possible misfile: "
                    f"'{validated.full_name}' not found in transcript header"
                )
                confidence = min(confidence, 0.3)

        if confidence < 0.6:
            review_reasons.append("low_extraction_confidence")

        # ── Fix 5: DOI verification ───────────────────────────────────────────
        pub_dois = [p.doi for p in validated.publications if p.doi]
        doi_validity: dict[str, bool | None] = {}
        if pub_dois:
            try:
                doi_validity = await verify_dois(pub_dois)
                invalid = [d for d, v in doi_validity.items() if v is False]
                if invalid:
                    short = ", ".join(invalid[:3])
                    suffix = f" (+{len(invalid)-3} more)" if len(invalid) > 3 else ""
                    logger.warning(f"⚠️ [{applicant_id}] Invalid DOIs: {short}{suffix}")
                    review_reasons.append(f"invalid_dois:{short}{suffix}")
            except Exception as e:
                logger.warning(f"DOI verification skipped: {e}")
        for doi, valid in doi_validity.items():
            if valid is True:
                DOI_VERIFICATIONS.labels(result="valid").inc()
            elif valid is False:
                DOI_VERIFICATIONS.labels(result="invalid").inc()
            else:
                DOI_VERIFICATIONS.labels(result="timeout").inc()

        model_name = getattr(orchestrator, "model", os.getenv("LLM_PROVIDER", "groq"))

        metrics_payload = {
            "bsc_uni_name":       (validated.bsc_uni or "")[:250] or None,
            "bsc_qs_rank":        bsc_rank,
            "bsc_gpa_raw":        to_float(validated.bsc_gpa.raw_value),
            "bsc_gpa_scale":      to_float(validated.bsc_gpa.scale, 4.0),
            # bsc_gpa_norm is on a 0-4.0 scale (normalise_gpa_to_4); the DB
            # column is documented/typed as a 0-1 fraction (Numeric(4,3),
            # see backend/app/db/models.py) and the dashboard renders it as
            # a 0-1 progress-bar width — divide down before storing.
            "bsc_gpa_normalised": round(bsc_gpa_norm / 4.0, 4) if bsc_gpa_norm is not None else None,
            "bsc_field":          (validated.bsc_field or "")[:200] or None,
            "bsc_country":        (validated.bsc_country or "")[:100] or None,
            "bsc_year":           validated.bsc_year,
            "msc_absent":         validated.msc_absent,
            "phd_uni_name":       (validated.phd_uni or "")[:250] or None,
            "phd_field":          (validated.phd_field or "")[:200] or None,
            "phd_year":           validated.phd_year,
            "phd_qs_rank":        phd_rank,
            "gre_verbal":         validated.gre_verbal,
            "gre_quant":          validated.gre_quant,
            "gre_awa":            validated.gre_awa,
            "ielts_score":        validated.ielts_score,
            "toefl_score":        validated.toefl_score,
            "work_exp_years":     validated.work_exp_years,
            "research_interests": validated.research_interests or None,
            "awards":             validated.awards or None,
            "llm_used":           True,
            "model_used":         model_name,
            "global_confidence":  confidence,
            "nlp_confidence_detail": {
                "review_reasons":    review_reasons,
                "misfile_suspected": misfile_detected,
                "cv_quality":        cv_quality,
                "cv_file_type":      cv_file_type,
                "doi_verification":  {
                    k: v for k, v in doi_validity.items() if v is not None
                },
            },
        }

        if not validated.msc_absent and validated.msc_uni:
            if validated.msc_gpa and validated.msc_gpa.raw_value:
                msc_gpa_norm = normalise_gpa_to_4(
                    validated.msc_gpa.raw_value,
                    validated.msc_gpa.scale or 4.0,
                    country=validated.msc_country,
                )
            metrics_payload.update({
                "msc_uni_name":       validated.msc_uni[:250],
                "msc_qs_rank":        msc_rank,
                "msc_gpa_raw":        to_float(validated.msc_gpa.raw_value) if validated.msc_gpa else None,
                "msc_gpa_scale":      to_float(validated.msc_gpa.scale, 4.0) if validated.msc_gpa else None,
                "msc_gpa_normalised": round(msc_gpa_norm / 4.0, 4) if msc_gpa_norm is not None else None,
                "msc_field":          (validated.msc_field or "")[:200] or None,
                "msc_country":        (validated.msc_country or "")[:100] or None,
                "msc_year":           validated.msc_year,
            })

        # ── Save publications ─────────────────────────────────────────────────
        pubs_to_save = []
        async with SessionLocal() as db:
            for idx, p in enumerate(validated.publications):
                if not p.title or p.title == "Untitled":
                    continue

                if p.venue:
                    pub_type, scopus_pct, rank_or_quartile, core_score = enrich_publication(
                        {"venue": p.venue}, df_scopus, df_core
                    )
                else:
                    pub_type = scopus_pct = rank_or_quartile = core_score = None

                if pub_type is None:
                    pub_type = p.pub_type or "journal"
                elif p.pub_type and p.pub_type in ("conference", "book_chapter", "preprint", "thesis"):
                    pub_type = p.pub_type

                scopus_quartile = rank_or_quartile if pub_type == "journal"    else None
                core_ranking    = rank_or_quartile if pub_type == "conference" else None

                pos = to_float(p.author_position, 1)
                tot = to_float(p.total_authors, 1)
                if tot <= 1:
                    contrib = 1.0
                elif pos == 1:
                    contrib = 1.0
                elif pos == tot and p.is_corresponding:
                    contrib = 0.85
                elif pos == tot:
                    contrib = 0.75
                else:
                    contrib = max(0.30, round(1.0 - (pos - 1) * 0.15, 2))

                venue_obj = await publication_repo.get_or_create_venue(
                    db,
                    venue_type=pub_type,
                    name=(p.venue or "Unknown")[:250],
                    scopus_pct=scopus_pct,
                    scopus_quartile=scopus_quartile,
                    core_ranking=core_ranking,
                    core_score=core_score,
                )

                pubs_to_save.append({
                    "title":                    (p.title or "Untitled")[:250],
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
                    "extraction_source":        "llm",
                    "position_in_cv":           idx + 1,
                    "doi":                      (p.doi or "")[:200] or None,
                    "under_review":             p.under_review,
                })
            await db.commit()

        # ── Final writes ──────────────────────────────────────────────────────
        async with SessionLocal() as db:
            await applicant_repo.upsert_extracted_metrics(db, app_uuid, metrics_payload)
            if pubs_to_save:
                await publication_repo.save_publications_batch(db, app_uuid, pubs_to_save)
            await applicant_repo.update_applicant_identity(
                db, app_uuid,
                full_name=validated.full_name or None,
                email=validated.email or None,
                nationality=validated.nationality or None,
                phone=validated.phone or None,
                linkedin=validated.linkedin or None,
                needs_human_review=(confidence < 0.6 or bool(review_reasons)),
            )
            await applicant_repo.reset_retry_count(db, app_uuid)
            await db.commit()

        # ── Supervisor matching ───────────────────────────────────────────────
        if validated.research_interests:
            try:
                await _match_supervisors(SessionLocal, app_uuid, validated.research_interests)
            except Exception as e:
                logger.warning(f"Supervisor matching skipped: {e}")

        logger.info(
            f"✅ [PIPELINE SUCCESS] {applicant_id} — "
            f"confidence={confidence} pubs={len(pubs_to_save)} "
            f"phd={bool(validated.phd_uni)} ielts={validated.ielts_score} "
            f"review_reasons={review_reasons}"
        )
        PIPELINE_RUNS.labels(status="success").inc()
        CONFIDENCE_SCORE.observe(confidence)
        for reason in review_reasons:
            REVIEW_REASONS.labels(reason=reason.split(":")[0]).inc()
        return True

    except Exception as e:
        PIPELINE_RUNS.labels(status="failed").inc()
        logger.error(f"❌ [PIPELINE CRASH] {applicant_id}: {e}", exc_info=True)
        async with SessionLocal() as db:
            await applicant_repo.increment_retry_count(db, app_uuid, str(e)[:500])
            await db.commit()
        return False

    finally:
        ACTIVE_PIPELINES.dec()
        PIPELINE_DURATION.observe(time.monotonic() - _pipeline_start)
        await orchestrator.close()
        await _release_lock(applicant_id)


def run_pipeline(applicant_id: str) -> bool:
    return asyncio.run(run_pipeline_logic(applicant_id))
