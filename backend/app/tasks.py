from celery import Celery

from src.pipeline.screening_pipeline import run_pipeline

celery = Celery(
    "tasks",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)


@celery.task
def process_documents_task(applicant_id: str):
    return run_pipeline(applicant_id)