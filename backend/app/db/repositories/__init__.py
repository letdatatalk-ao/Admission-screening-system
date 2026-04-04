"""
backend/app/db/repositories/__init__.py
Exports centralisés — importer depuis ici dans FastAPI et Celery.
"""

from .session_repo import (
    create_session,
    get_session,
    list_sessions,
    close_session,
    create_ranking_config,
    get_ranking_config,
    get_default_config,
    list_configs,
)

from .applicant_repo import (
    create_applicant,
    get_applicant,
    get_applicant_by_ref,
    list_applicants,
    update_applicant_status,
    update_applicant_documents,
    update_applicant_score,
    flag_review,
    upsert_extracted_metrics,
    get_extracted_metrics,
)

from .document_repo import (
    create_document,
    get_document,
    get_documents_for_applicant,
    update_ocr_quality,
    document_exists_by_hash,
)

from .publication_repo import (
    get_or_create_venue,
    get_venue,
    save_publication,
    save_publications_batch,
    list_publications,
    count_publications,
)

from .scoring_repo import (
    save_ranking_result,
    save_ranking_and_update_applicants,
    get_latest_ranking,
    list_ranking_history,
    save_manual_override,
    list_overrides,
    log_action,
    get_audit_trail,
)

__all__ = [
    # session
    "create_session", "get_session", "list_sessions", "close_session",
    "create_ranking_config", "get_ranking_config", "get_default_config", "list_configs",
    # applicant
    "create_applicant", "get_applicant", "get_applicant_by_ref", "list_applicants",
    "update_applicant_status", "update_applicant_documents", "update_applicant_score",
    "flag_review", "upsert_extracted_metrics", "get_extracted_metrics",
    # document
    "create_document", "get_document", "get_documents_for_applicant",
    "update_ocr_quality", "document_exists_by_hash",
    # publication
    "get_or_create_venue", "get_venue", "save_publication",
    "save_publications_batch", "list_publications", "count_publications",
    # scoring
    "save_ranking_result", "save_ranking_and_update_applicants",
    "get_latest_ranking", "list_ranking_history",
    "save_manual_override", "list_overrides",
    "log_action", "get_audit_trail",
]