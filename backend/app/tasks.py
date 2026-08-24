"""
backend/app/tasks.py

FIX 1: retry_pending_cvs was registered as 'tasks.retry_pending_cvs' by beat
        but the worker loaded it as 'backend.app.tasks.retry_pending_cvs'.
        Solution: set the task name explicitly with name= parameter.

FIX 2: asyncio.run() inside retry_pending_cvs also needs a fresh engine,
        same root cause as the pipeline. We reuse the same pattern.
"""

import asyncio
import os

from celery import Celery
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from src.pipeline.screening_pipeline import run_pipeline

logger = get_task_logger(__name__)

celery = Celery(
    "tasks",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=600,
    task_time_limit=720,
    task_default_retry_delay=30,
    task_max_retries=3,
    beat_schedule={
        'retry-pending-cvs': {
            # ✅ FIX: Must match the 'name=' on the task decorator below.
            # Beat was sending 'tasks.retry_pending_cvs' but the worker
            # registered it as 'backend.app.tasks.retry_pending_cvs' → KeyError.
            'task': 'backend.app.tasks.retry_pending_cvs',
            'schedule': 60.0,
        },
    },
)


@celery.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="backend.app.tasks.process_documents_task",  # ✅ explicit name
)
def process_documents_task(self, applicant_id: str) -> bool:
    """Main task: process a single applicant's CV + transcript."""
    logger.info(f"[TASK START] applicant_id={applicant_id} attempt={self.request.retries + 1}")

    try:
        success = run_pipeline(applicant_id)
        if success:
            logger.info(f"[TASK SUCCESS] applicant_id={applicant_id}")
        else:
            logger.error(f"[TASK FAILED] applicant_id={applicant_id}")
        return success
    except Exception as exc:
        logger.error(f"[TASK ERROR] applicant_id={applicant_id}: {exc}")
        if self.request.retries < 3:
            raise self.retry(exc=exc)
        return False


@celery.task(name="backend.app.tasks.retry_pending_cvs")  # ✅ explicit name
def retry_pending_cvs():
    """
    Periodic task: scan for pending/error applicants and requeue them.
    
    ✅ FIX: Uses a fresh engine (not the shared pool) because this runs
    inside asyncio.run(), which creates a new event loop each time.
    """
    logger.info("🔄 Scanning for pending/error CVs to retry...")

    async def _scan():
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:password@postgres:5432/pg_screening"
        )
        engine = create_async_engine(database_url, pool_size=2, max_overflow=0)
        SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT id FROM applicants
                        WHERE retry_count < 5
                          AND (
                            status IN ('pending', 'error')
                            OR (
                              -- Récupère les jobs bloqués en "processing"
                              -- si le worker est mort sans mettre à jour le statut.
                              -- NULL last_attempt_at (row never timestamped) must
                              -- also match — `NULL < anything` is never TRUE in SQL,
                              -- so without the IS NULL branch these rows are stuck forever.
                              status = 'processing'
                              AND (last_attempt_at IS NULL OR last_attempt_at < NOW() - INTERVAL '30 minutes')
                            )
                          )
                        ORDER BY retry_count ASC, created_at ASC
                    """)
                )
                return [str(row[0]) for row in result.fetchall()]
        finally:
            await engine.dispose()

    try:
        pending_ids = asyncio.run(_scan())

        if pending_ids:
            logger.info(f"📋 Found {len(pending_ids)} CVs to retry")
            for app_id in pending_ids:
                process_documents_task.delay(app_id)
        else:
            logger.info("✅ No CVs to retry")

    except Exception as e:
        logger.error(f"❌ Error in retry_pending_cvs: {e}", exc_info=True)