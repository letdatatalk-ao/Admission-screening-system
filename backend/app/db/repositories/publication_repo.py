"""
backend/app/db/repositories/publication_repo.py

CRUD pour Publications et Venues.
"""

from __future__ import annotations

import uuid
from typing import Optional, List

from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Publication, Venue


# ============================================================================
# Venue
# ============================================================================

async def get_or_create_venue(
    db: AsyncSession,
    venue_type: str,
    name: str,
    acronym: Optional[str] = None
) -> Venue:
    """Récupère un venue existant ou en crée un nouveau."""
    result = await db.execute(
        select(Venue).where(Venue.name == name, Venue.venue_type == venue_type)
    )
    venue = result.scalar_one_or_none()
    
    if not venue:
        venue = Venue(
            venue_type=venue_type,
            name=name,
            acronym=acronym
        )
        db.add(venue)
        await db.flush()
    
    return venue


async def get_venue(db: AsyncSession, venue_id: uuid.UUID) -> Optional[Venue]:
    """Récupère un venue par son ID."""
    result = await db.execute(select(Venue).where(Venue.id == venue_id))
    return result.scalar_one_or_none()


# ============================================================================
# Publication
# ============================================================================

async def create_publication(
    db: AsyncSession,
    applicant_id: uuid.UUID,
    venue_id: Optional[uuid.UUID],
    pub_type: str,
    position_in_cv: int,
    title: Optional[str] = None,
    authors_raw: Optional[str] = None,
    author_position: Optional[int] = None,
    total_authors: Optional[int] = None,
    contribution_score: Optional[float] = None,
    year: Optional[int] = None,
    extraction_source: str = "nlp"
) -> Publication:
    """Crée une nouvelle publication."""
    pub = Publication(
        applicant_id=applicant_id,
        venue_id=venue_id,
        pub_type=pub_type,
        position_in_cv=position_in_cv,
        title=title,
        authors_raw=authors_raw,
        author_position=author_position,
        total_authors=total_authors,
        contribution_score=contribution_score,
        year=year,
        extraction_source=extraction_source
    )
    db.add(pub)
    await db.flush()
    await db.refresh(pub)
    return pub


async def save_publication(db: AsyncSession, publication_data: dict) -> Publication:
    """Alias pour create_publication - utilisé par l'import __init__.py"""
    return await create_publication(
        db=db,
        applicant_id=publication_data.get("applicant_id"),
        venue_id=publication_data.get("venue_id"),
        pub_type=publication_data.get("pub_type", "journal"),
        position_in_cv=publication_data.get("position_in_cv", 999),
        title=publication_data.get("title"),
        authors_raw=publication_data.get("authors_raw"),
        author_position=publication_data.get("author_position"),
        total_authors=publication_data.get("total_authors"),
        contribution_score=publication_data.get("contribution_score", 0.5),
        year=publication_data.get("year"),
        extraction_source=publication_data.get("extraction_source", "manual")
    )


async def get_publication(db: AsyncSession, publication_id: uuid.UUID) -> Optional[Publication]:
    """Récupère une publication par son ID."""
    result = await db.execute(
        select(Publication).where(Publication.id == publication_id)
    )
    return result.scalar_one_or_none()


async def list_publications(
    db: AsyncSession,
    applicant_id: uuid.UUID
) -> List[Publication]:
    """Liste toutes les publications d'un candidat avec la relation venue chargée."""
    result = await db.execute(
        select(Publication)
        .options(selectinload(Publication.venue))  # ✅ Charge la relation venue
        .where(Publication.applicant_id == applicant_id)
        .order_by(Publication.position_in_cv)
    )
    return list(result.scalars().all())


async def count_publications(
    db: AsyncSession,
    applicant_id: uuid.UUID
) -> int:
    """Compte le nombre de publications d'un candidat."""
    result = await db.execute(
        select(func.count(Publication.id)).where(Publication.applicant_id == applicant_id)
    )
    return result.scalar() or 0


async def update_publication(
    db: AsyncSession,
    publication_id: uuid.UUID,
    data: dict
) -> bool:
    """Met à jour une publication."""
    result = await db.execute(
        update(Publication)
        .where(Publication.id == publication_id)
        .values(**data)
    )
    return result.rowcount > 0


async def delete_publication(
    db: AsyncSession,
    publication_id: uuid.UUID
) -> bool:
    """Supprime une publication."""
    result = await db.execute(
        delete(Publication).where(Publication.id == publication_id)
    )
    return result.rowcount > 0


async def save_publications_batch(
    db: AsyncSession,
    applicant_id: uuid.UUID,
    pubs_data: List[dict]
) -> List[Publication]:
    """Sauvegarde un lot de publications en une seule transaction."""
    publications = []
    for pub_data in pubs_data:
        pub = Publication(
            applicant_id=applicant_id,
            **pub_data
        )
        db.add(pub)
        publications.append(pub)
    
    await db.flush()
    return publications