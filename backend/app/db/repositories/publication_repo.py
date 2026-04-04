"""
backend/app/db/repositories/publication_repo.py

CRUD pour Publication et Venue.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Publication, Venue


# ---------------------------------------------------------------------------
# Venue  (journaux / conférences référencés)
# ---------------------------------------------------------------------------

async def get_or_create_venue(
    db:               AsyncSession,
    venue_type:       str,              # "journal" | "conference"
    name:             str,
    acronym:          Optional[str]  = None,
    scopus_pct:       Optional[float] = None,
    scopus_quartile:  Optional[str]  = None,
    core_ranking:     Optional[str]  = None,
    core_score:       Optional[int]  = None,
    lookup_source:    Optional[str]  = None,
    lookup_confidence: Optional[float] = None,
) -> Venue:
    """
    Retourne un Venue existant (même type + nom) ou en crée un nouveau.
    Évite les doublons dans la table venues.
    """
    result = await db.execute(
        select(Venue).where(
            Venue.venue_type == venue_type,
            Venue.name == name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    venue = Venue(
        venue_type=venue_type,
        name=name,
        acronym=acronym,
        scopus_pct=scopus_pct,
        scopus_quartile=scopus_quartile,
        core_ranking=core_ranking,
        core_score=core_score,
        lookup_source=lookup_source,
        lookup_confidence=lookup_confidence,
    )
    db.add(venue)
    await db.flush()
    await db.refresh(venue)
    return venue


async def get_venue(
    db:       AsyncSession,
    venue_id: uuid.UUID,
) -> Optional[Venue]:
    result = await db.execute(
        select(Venue).where(Venue.id == venue_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

async def save_publication(
    db:                       AsyncSession,
    applicant_id:             uuid.UUID,
    pub_type:                 str,           # "journal" | "conference"
    position_in_cv:           int,
    title:                    Optional[str]   = None,
    authors_raw:              Optional[str]   = None,
    author_position:          Optional[int]   = None,
    total_authors:            Optional[int]   = None,
    first_author:             Optional[bool]  = None,
    contribution_score:       Optional[float] = None,
    year:                     Optional[int]   = None,
    raw_citation:             Optional[str]   = None,
    venue_id:                 Optional[uuid.UUID] = None,
    scopus_pct_at_extraction: Optional[float] = None,
    core_score_at_extraction: Optional[int]   = None,
    confidence:               Optional[float] = None,
    extraction_source:        str             = "nlp",
) -> Publication:
    """Insère une publication extraite pour un candidat."""
    pub = Publication(
        applicant_id=applicant_id,
        venue_id=venue_id,
        pub_type=pub_type,
        position_in_cv=position_in_cv,
        title=title,
        authors_raw=authors_raw,
        author_position=author_position,
        total_authors=total_authors,
        first_author=first_author,
        contribution_score=contribution_score,
        year=year,
        raw_citation=raw_citation,
        scopus_pct_at_extraction=scopus_pct_at_extraction,
        core_score_at_extraction=core_score_at_extraction,
        confidence=confidence,
        extraction_source=extraction_source,
    )
    db.add(pub)
    await db.flush()
    await db.refresh(pub)
    return pub


async def save_publications_batch(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
    publications: list[dict],
) -> list[Publication]:
    """
    Insère toutes les publications d'un candidat en un seul appel.
    Supprime d'abord les anciennes (re-extraction).

    Chaque dict dans `publications` doit avoir les clés :
        pub_type, position_in_cv, venue_id (optionnel),
        title, authors_raw, author_position, total_authors,
        first_author, contribution_score, year, raw_citation,
        scopus_pct_at_extraction, core_score_at_extraction,
        confidence, extraction_source

    Usage depuis tasks.py (Celery) :
        pubs_data = [
            {
                "pub_type": "conference",
                "position_in_cv": 1,
                "title": "Enhancing IoT Security...",
                "author_position": 1,
                "total_authors": 2,
                "first_author": True,
                "contribution_score": 1.0,
                "year": 2023,
                "venue_id": venue.id,
                "core_score_at_extraction": 3,
                "confidence": 0.59,
                "extraction_source": "nlp",
            }
        ]
        await save_publications_batch(db, applicant_id, pubs_data)
    """
    # Supprime les publications existantes pour ce candidat (re-run propre)
    await db.execute(
        delete(Publication).where(Publication.applicant_id == applicant_id)
    )

    saved = []
    for i, pub_data in enumerate(publications):
        pub = await save_publication(
            db=db,
            applicant_id=applicant_id,
            position_in_cv=pub_data.get("position_in_cv", i + 1),
            **{k: v for k, v in pub_data.items() if k != "position_in_cv"},
        )
        saved.append(pub)

    return saved


async def list_publications(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
    pub_type:     Optional[str] = None,   # "journal" | "conference" | None
) -> list[Publication]:
    """Liste les publications d'un candidat, filtrées par type si fourni."""
    q = (
        select(Publication)
        .where(Publication.applicant_id == applicant_id)
        .order_by(Publication.position_in_cv)
    )
    if pub_type:
        q = q.where(Publication.pub_type == pub_type)
    result = await db.execute(q)
    return list(result.scalars().all())


async def count_publications(
    db:           AsyncSession,
    applicant_id: uuid.UUID,
) -> dict[str, int]:
    """Retourne {"journal": N, "conference": M} pour un candidat."""
    all_pubs = await list_publications(db, applicant_id)
    return {
        "journal":    sum(1 for p in all_pubs if p.pub_type == "journal"),
        "conference": sum(1 for p in all_pubs if p.pub_type == "conference"),
    }