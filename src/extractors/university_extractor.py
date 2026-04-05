"""
Extraction et enrichment des universités à partir des CSV QS rankings.
Utilise rapidfuzz pour le matching flou des noms d'universités.
"""
from rapidfuzz import process, fuzz
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def lookup_qs_rank(detected_name, df_qs, qs_names):
    """
    Cherche le classement QS d'une université.
    
    Args:
        detected_name: Nom détecté de l'université
        df_qs: DataFrame QS avec colonnes 'rank', 'university_name', 'country'
        qs_names: Liste des noms d'universités dans le classement
    
    Returns:
        int: Le rang QS ou None si non trouvé
    """
    if not detected_name or df_qs is None or df_qs.empty:
        return None
    
    # Nettoyer le nom
    name_clean = detected_name.strip()
    
    try:
        # Matching flou avec token_set_ratio (bon pour les noms d'universités)
        res = process.extractOne(
            name_clean, 
            qs_names, 
            scorer=fuzz.token_set_ratio, 
            score_cutoff=80
        )
        
        if res:
            matched_name, score, _ = res
            row = df_qs[df_qs['university_name'] == matched_name]
            
            if not row.empty:
                rank = int(row.iloc[0]['rank'])
                logger.debug(f"QS match: '{name_clean}' → '{matched_name}' (rank={rank}, score={score})")
                return rank
            else:
                logger.debug(f"QS match found but row empty for: '{matched_name}'")
        else:
            logger.debug(f"No QS match found for: '{name_clean}'")
            
    except Exception as e:
        logger.warning(f"QS lookup error for '{detected_name}': {e}")
    
    return None


def get_university_country(detected_name, df_qs, qs_names):
    """
    Cherche le pays d'une université.
    
    Args:
        detected_name: Nom détecté de l'université
        df_qs: DataFrame QS avec colonnes 'rank', 'university_name', 'country'
        qs_names: Liste des noms d'universités dans le classement
    
    Returns:
        str: Le pays ou None si non trouvé
    """
    if not detected_name or df_qs is None or df_qs.empty:
        return None
    
    name_clean = detected_name.strip()
    
    try:
        res = process.extractOne(
            name_clean, 
            qs_names, 
            scorer=fuzz.token_set_ratio, 
            score_cutoff=80
        )
        
        if res:
            matched_name, score, _ = res
            row = df_qs[df_qs['university_name'] == matched_name]
            
            if not row.empty and 'country' in row.columns:
                country = row.iloc[0]['country']
                logger.debug(f"Country match: '{name_clean}' → '{country}'")
                return country
                
    except Exception as e:
        logger.warning(f"Country lookup error for '{detected_name}': {e}")
    
    return None


def get_qs_normalised_score(rank: int) -> float:
    """
    Convertit un rang QS en score normalisé (0-100).
    
    Formule: rank 1 → 100, rank 1000 → 10, décroissance logarithmique
    """
    if rank is None or rank <= 0:
        return 15.0  # Valeur par défaut pour université non classée
    
    # Normalisation: plus le rang est bas, plus le score est élevé
    # Rang 1 → 100, Rang 100 → 91, Rang 1000 → 10
    score = max(10.0, 100.0 - (rank - 1.0) * 0.09)
    return round(score, 2)