from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

celery = Celery(
    "pgars",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

@celery.task
def extract_task(cv_path: str, transcript_path: str, applicant_id: str):
    return {"status": "stub", "applicant_id": applicant_id}