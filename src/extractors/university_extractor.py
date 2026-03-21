import re
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from rapidfuzz import process, fuzz
import spacy

nlp = spacy.load("en_core_web_lg")

ALIASES = {
    "MIT":  "Massachusetts Institute of Technology",
    "UCL":  "UCL",
    "LSE":  "London School of Economics",
    "EPFL": "EPFL",
    "NYU":  "New York University",
    "UCLA": "University of California Los Angeles",
    "UCSD": "University of California San Diego",
    "UCB":  "University of California Berkeley",
    "SEMO": "Southeast Missouri State University",
}

UNIVERSITY_REGEX = re.compile(
    r'(?:university|université|institute|college|school|academy|polytechnic)'
    r'[^,\n]{0,60}',
    re.IGNORECASE
)

DEGREE_WORDS = re.compile(
    r'\b(bachelor|master|doctor|phd|b\.sc|m\.sc|'
    r'degree|science|engineering|cybersecurity)\b',
    re.IGNORECASE
)


@dataclass
class UniversityResult:
    detected_name:  Optional[str]
    qs_rank:        Optional[int]
    qs_match_name:  Optional[str]
    match_score:    float
    confidence:     float
    degree_level:   str


def load_qs_db(csv_path: str) -> tuple:
    df = pd.read_csv(csv_path)
    return df, df['university_name'].tolist()


def clean_candidate(text: str) -> str:
    text = text.split(',')[0].strip()
    text = re.sub(
        r'\s+(Abu Dhabi|UAE|New York|London|Paris|Beijing).*$',
        '', text, flags=re.IGNORECASE)
    return text.strip()


def extract_university(text: str,
                       df_qs: pd.DataFrame,
                       qs_names: list,
                       degree_level: str = "unknown") -> UniversityResult:
    if not text or len(text.strip()) < 10:
        return UniversityResult(None, None, None, 0.0, 0.0, degree_level)

    # 1. Alias
    for alias, full_name in ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', text):
            row = df_qs[df_qs['university_name'] == full_name]
            rank = int(row.iloc[0]['rank']) if len(row) > 0 else None
            return UniversityResult(full_name, rank, full_name,
                                    1.0, 0.95, degree_level)

    # 2. Regex
    candidates = []
    for line in text.split('\n'):
        line = line.strip()
        if UNIVERSITY_REGEX.search(line) and not DEGREE_WORDS.search(line):
            candidates.append(clean_candidate(line))

    # 3. spaCy fallback
    if not candidates:
        doc = nlp(text[:2000])
        candidates = [clean_candidate(e.text)
                      for e in doc.ents if e.label_ == "ORG"]

    if not candidates:
        return UniversityResult(None, None, None, 0.0, 0.0, degree_level)

    # 4. Fuzzy match
    best_name, best_rank, best_score, best_match = None, None, 0.0, None
    for candidate in candidates:
        result = process.extractOne(
            candidate, qs_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=85
        )
        if result and result[1] > best_score:
            best_score = result[1]
            best_match = result[0]
            row = df_qs[df_qs['university_name'] == best_match]
            best_rank = int(row.iloc[0]['rank']) if len(row) > 0 else None
            best_name = candidate

    # 5. Non classée
    if best_score == 0:
        return UniversityResult(
            detected_name=candidates[0],
            qs_rank=None,
            qs_match_name=None,
            match_score=0.0,
            confidence=0.10,
            degree_level=degree_level
        )

    return UniversityResult(
        detected_name=best_name,
        qs_rank=best_rank,
        qs_match_name=best_match,
        match_score=round(best_score / 100, 2),
        confidence=round(best_score / 100, 2),
        degree_level=degree_level
    )

def split_bsc_msc(education_text: str) -> dict:
    """Sépare le texte EDUCATION en parties BSc et MSc."""
    bsc_keywords = r'(?i)(bachelor|b\.sc|bsc|b\.s\.|undergraduate|licence)'
    msc_keywords = r'(?i)(master|m\.sc|msc|m\.s\.|postgraduate)'

    lines = education_text.split('\n')
    bsc_lines, msc_lines = [], []
    current = None

    for line in lines:
        if re.search(msc_keywords, line):
            current = 'msc'
        elif re.search(bsc_keywords, line):
            current = 'bsc'
        if current == 'bsc':
            bsc_lines.append(line)
        elif current == 'msc':
            msc_lines.append(line)

    return {
        "bsc": '\n'.join(bsc_lines),
        "msc": '\n'.join(msc_lines)
    }

def split_bsc_msc(education_text: str) -> dict:
    """Sépare le texte EDUCATION en parties BSc et MSc."""
    import re
    bsc_keywords = r'(?i)(bachelor|b\.sc|bsc|b\.s\.|undergraduate|licence)'
    msc_keywords = r'(?i)(master|m\.sc|msc|m\.s\.|postgraduate)'
    lines = education_text.split('\n')
    bsc_lines, msc_lines = [], []
    current = None
    for line in lines:
        if re.search(msc_keywords, line):
            current = 'msc'
        elif re.search(bsc_keywords, line):
            current = 'bsc'
        if current == 'bsc':
            bsc_lines.append(line)
        elif current == 'msc':
            msc_lines.append(line)
    return {"bsc": '\n'.join(bsc_lines), "msc": '\n'.join(msc_lines)}
