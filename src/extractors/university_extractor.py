from rapidfuzz import process, fuzz
import pandas as pd

def lookup_qs_rank(detected_name, df_qs, qs_names):
    if not detected_name: return None
    res = process.extractOne(detected_name, qs_names, scorer=fuzz.token_set_ratio, score_cutoff=80)
    if res:
        row = df_qs[df_qs['university_name'] == res[0]]
        return int(row.iloc[0]['rank'])
    return None