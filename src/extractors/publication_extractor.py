"""
Extraction et enrichissement des publications à partir des CSV.
Utilise rapidfuzz pour le matching flou des noms de journaux/conférences.
"""
from rapidfuzz import process, fuzz
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def enrich_publication(pub_data, df_scopus, df_core):
    """
    Enrichit une publication avec les scores Scopus et CORE.
    
    Args:
        pub_data: dict avec au moins 'venue' (nom du journal/conference)
        df_scopus: DataFrame Scopus avec colonnes 'journal_name', 'scopus_pct', 'sjr_quartile'
        df_core: DataFrame CORE avec colonnes 'conference_name', 'core_rank', 'core_score'
    
    Returns:
        tuple: (pub_type, scopus_pct, core_rank, core_score)
        - pub_type: 'journal' ou 'conference'
        - scopus_pct: percentile Scopus (0-100) ou None si non trouvé
        - core_rank: classement CORE ('A*', 'A', 'B', 'C') ou None si non trouvé
        - core_score: score CORE (10, 8, 5, 3) ou None si non trouvé
    """
    # Cas 1: Données de publication manquantes
    if not pub_data:
        logger.debug("Publication data missing, returning default")
        return "journal", None, None, None
    
    venue_name = pub_data.get('venue', '')
    
    # Cas 2: Nom du lieu manquant ou invalide
    if not venue_name or venue_name == "Unknown":
        logger.debug(f"Venue name missing or invalid: '{venue_name}', returning default")
        return "journal", None, None, None
    
    # Nettoyer le nom pour le matching
    venue_clean = venue_name.strip()
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. TENTER UN MATCH SCOPUS (JOURNAL)
    # ─────────────────────────────────────────────────────────────────────────
    if df_scopus is not None and not df_scopus.empty:
        try:
            # Vérifier que la colonne journal_name existe
            if 'journal_name' in df_scopus.columns:
                journal_list = df_scopus['journal_name'].fillna('').tolist()
                
                # Matching flou avec token_set_ratio (insensible à l'ordre des mots)
                scopus_match = process.extractOne(
                    venue_clean, 
                    journal_list, 
                    scorer=fuzz.token_set_ratio, 
                    score_cutoff=80
                )
                
                if scopus_match:
                    matched_name, score, _ = scopus_match
                    row = df_scopus[df_scopus['journal_name'] == matched_name].iloc[0]
                    
                    # Extraire le percentile Scopus
                    scopus_pct = None
                    if 'scopus_pct' in row and pd.notna(row['scopus_pct']):
                        try:
                            scopus_pct = float(row['scopus_pct'])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid scopus_pct value: {row['scopus_pct']}")
                    
                    # Extraire le quartile
                    quartile = None
                    if 'sjr_quartile' in row and pd.notna(row['sjr_quartile']):
                        quartile = row['sjr_quartile']
                    
                    logger.info(f"✅ Scopus match: '{venue_clean}' → '{matched_name}' (score={score}, pct={scopus_pct}, quartile={quartile})")
                    return "journal", scopus_pct, quartile, None
                    
        except Exception as e:
            logger.warning(f"Scopus lookup error for '{venue_name}': {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. TENTER UN MATCH CORE (CONFÉRENCE)
    # ─────────────────────────────────────────────────────────────────────────
    if df_core is not None and not df_core.empty:
        try:
            # 2a. Matching par nom de conférence
            if 'conference_name' in df_core.columns:
                conf_list = df_core['conference_name'].fillna('').tolist()
                
                core_match = process.extractOne(
                    venue_clean, 
                    conf_list, 
                    scorer=fuzz.token_set_ratio, 
                    score_cutoff=80
                )
                
                if core_match:
                    matched_name, score, _ = core_match
                    row = df_core[df_core['conference_name'] == matched_name].iloc[0]
                    
                    # Extraire le rang CORE
                    core_rank = None
                    if 'core_rank' in row and pd.notna(row['core_rank']):
                        core_rank = row['core_rank']
                    
                    # Extraire le score CORE
                    core_score = None
                    if 'core_score' in row and pd.notna(row['core_score']):
                        try:
                            core_score = int(row['core_score'])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid core_score value: {row['core_score']}")
                    
                    logger.info(f"✅ CORE match: '{venue_clean}' → '{matched_name}' (score={score}, rank={core_rank}, score_val={core_score})")
                    return "conference", None, core_rank, core_score
            
            # 2b. Matching par acronyme
            if 'acronym' in df_core.columns:
                acronym_list = df_core['acronym'].fillna('').tolist()
                acronym_match = process.extractOne(
                    venue_clean, 
                    acronym_list, 
                    scorer=fuzz.token_set_ratio, 
                    score_cutoff=85
                )
                
                if acronym_match:
                    matched_acronym, score, _ = acronym_match
                    row = df_core[df_core['acronym'] == matched_acronym].iloc[0]
                    
                    core_rank = None
                    if 'core_rank' in row and pd.notna(row['core_rank']):
                        core_rank = row['core_rank']
                    
                    core_score = None
                    if 'core_score' in row and pd.notna(row['core_score']):
                        try:
                            core_score = int(row['core_score'])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid core_score value: {row['core_score']}")
                    
                    logger.info(f"✅ CORE acronym match: '{venue_clean}' → acronym '{matched_acronym}' (rank={core_rank}, score={core_score})")
                    return "conference", None, core_rank, core_score
                    
        except Exception as e:
            logger.warning(f"CORE lookup error for '{venue_name}': {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. AUCUN MATCH TROUVÉ
    # ─────────────────────────────────────────────────────────────────────────
    logger.debug(f"❌ No match found for venue: '{venue_name}'")
    return "journal", None, None, None