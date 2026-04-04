from rapidfuzz import process, fuzz
import pandas as pd

def enrich_publication(pub_data, df_scopus, df_core):
    """Prend une pub du LLM et ajoute les scores Scopus/CORE."""
    venue_name = pub_data['venue']
    
    # 1. Tenter un match Scopus (Journal)
    scopus_match = process.extractOne(venue_name, df_scopus['journal_name'].tolist(), score_cutoff=85)
    if scopus_match:
        row = df_scopus[df_scopus['journal_name'] == scopus_match[0]].iloc[0]
        return "journal", float(row['scopus_pct']), None, None

    # 2. Tenter un match CORE (Conférence)
    core_match = process.extractOne(venue_name, df_core['conference_name'].tolist(), score_cutoff=85)
    if core_match:
        row = df_core[df_core['conference_name'] == core_match[0]].iloc[0]
        return "conference", None, row['core_rank'], int(row['core_score'])

    return "journal", 0.0, None, 0 # Non classé