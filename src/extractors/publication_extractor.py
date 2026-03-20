import re
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List
from rapidfuzz import process, fuzz


@dataclass
class VenueResult:
    name:         Optional[str]
    matched_name: Optional[str]
    venue_type:   str
    scopus_pct:   Optional[float]
    scopus_q:     Optional[str]
    core_rank:    Optional[str]
    core_score:   Optional[int]
    match_score:  float
    confidence:   float


@dataclass
class PublicationResult:
    raw_citation:       str
    title:              Optional[str]
    year:               Optional[int]
    authors_raw:        Optional[str]
    author_position:    Optional[int]
    total_authors:      Optional[int]
    first_author:       bool
    contribution_score: float
    venue:              VenueResult
    confidence:         float
    extraction_source:  str


PATTERNS = [
    re.compile(
        r'(?P<authors>[A-Z][A-Za-z\s\-,\.&]+?)\s*\((?P<year>\d{4})\)\.\s*'
        r'(?P<title>[^.]{15,150})\.\s*[Ii]n\s+[Pp]roceedings\s+of\s+'
        r'(?P<venue>[^,\n\.]{10,120})',
        re.DOTALL
    ),
    re.compile(
        r'(?P<authors>[A-Z][A-Za-z\s\-,\.&]+?)\s*\((?P<year>\d{4})\)\.\s*'
        r'(?P<title>[^.]{15,150})\.\s*(?P<venue>[A-Z][^,\n]{5,80})',
        re.DOTALL
    ),
    re.compile(
        r'\[\d+\]\s*(?P<authors>[A-Z][^"]{5,80}),\s*'
        r'"(?P<title>[^"]{10,120})",\s*'
        r'(?P<venue>[^,\n]{5,80})[,\s]*(?P<year>\d{4})',
        re.DOTALL
    ),
]

JOURNAL_KW = re.compile(
    r'\b(journal|transactions|letters|review|IEEE Trans|ACM Trans)\b',
    re.IGNORECASE)
CONFERENCE_KW = re.compile(
    r'\b(conference|proceedings|symposium|workshop|congress|'
    r'CVPR|NeurIPS|ICML|ICLR|AAAI|IJCAI|CCS|NDSS|INFOCOM|ICITST)\b',
    re.IGNORECASE)


def load_reference_data(scopus_path: str,
                         core_path: str) -> tuple:
    df_s = pd.read_csv(scopus_path)
    df_c = pd.read_csv(core_path)
    return df_s, df_c


def lookup_scopus(venue_name: str,
                  df_scopus: pd.DataFrame) -> VenueResult:
    names = df_scopus['journal_name'].tolist()
    result = process.extractOne(venue_name, names,
                                scorer=fuzz.token_set_ratio,
                                score_cutoff=80)
    if result:
        row = df_scopus[df_scopus['journal_name'] == result[0]].iloc[0]
        return VenueResult(
            name=venue_name, matched_name=row['journal_name'],
            venue_type="journal",
            scopus_pct=float(row['scopus_pct']),
            scopus_q=row['sjr_quartile'],
            core_rank=None, core_score=None,
            match_score=round(result[1]/100, 2),
            confidence=round(result[1]/100, 2))
    return VenueResult(venue_name, None, "journal",
                       None, None, None, None, 0.0, 0.10)


def lookup_core(venue_name: str,
                df_core: pd.DataFrame) -> VenueResult:
    names    = df_core['conference_name'].tolist()
    acronyms = df_core['acronym'].tolist()
    r1 = process.extractOne(venue_name, names,
                             scorer=fuzz.token_set_ratio, score_cutoff=75)
    r2 = process.extractOne(venue_name, acronyms,
                             scorer=fuzz.token_set_ratio, score_cutoff=90)
    result, use_acronym = None, False
    if r1 and r2:
        result, use_acronym = (r1, False) if r1[1] >= r2[1] else (r2, True)
    elif r1: result = r1
    elif r2: result, use_acronym = r2, True

    if result:
        col = 'acronym' if use_acronym else 'conference_name'
        row = df_core[df_core[col] == result[0]].iloc[0]
        return VenueResult(
            name=venue_name, matched_name=row['conference_name'],
            venue_type="conference",
            scopus_pct=None, scopus_q=None,
            core_rank=row['core_rank'],
            core_score=int(row['core_score']),
            match_score=round(result[1]/100, 2),
            confidence=round(result[1]/100, 2))
    return VenueResult(venue_name, None, "conference",
                       None, None, None, None, 0.0, 0.10)


def parse_author_position(authors_raw: str,
                           candidate_hint: str = "") -> tuple:
    parts = re.split(r'\s*&\s*|\s*;\s*|,\s*(?=[A-Z][a-z])', authors_raw)
    parts = [p.strip() for p in parts
             if p.strip() and len(p.strip()) > 3]
    total = len(parts)
    if total == 0:
        return None, None
    for i, author in enumerate(parts):
        if any(tok.lower() in author.lower()
               for tok in candidate_hint.replace('-', ' ').split()):
            return i + 1, total
    return 1, total


def contribution_score(pos: int, total: int) -> float:
    if not pos or not total:
        return 0.5
    if pos == total and total > 1:
        return 0.85
    return round((total - pos + 1) / total, 3)


def extract_publications(text: str,
                          df_scopus: pd.DataFrame,
                          df_core: pd.DataFrame,
                          candidate_hint: str = "") -> List[PublicationResult]:
    results = []
    used = []

    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            start = m.start()
            if any(abs(start - u) < 80 for u in used):
                continue
            used.append(start)

            authors = m.groupdict().get('authors', '').strip()
            title   = m.groupdict().get('title',   '').strip()
            venue_r = m.groupdict().get('venue',   '').strip()
            yr_str  = m.groupdict().get('year',    '')
            year    = int(yr_str) if yr_str.isdigit() else None

            if CONFERENCE_KW.search(venue_r) or CONFERENCE_KW.search(text[:300]):
                venue = lookup_core(venue_r, df_core)
            elif JOURNAL_KW.search(venue_r):
                venue = lookup_scopus(venue_r, df_scopus)
            else:
                vj = lookup_scopus(venue_r, df_scopus)
                vc = lookup_core(venue_r, df_core)
                venue = vj if vj.confidence >= vc.confidence else vc

            pos, total = parse_author_position(authors, candidate_hint)
            contrib    = contribution_score(pos, total)
            conf       = round(0.55 + venue.confidence * 0.35, 2)

            results.append(PublicationResult(
                raw_citation=m.group(0)[:250],
                title=title[:120] if title else None,
                year=year,
                authors_raw=authors[:150] if authors else None,
                author_position=pos,
                total_authors=total,
                first_author=(pos == 1),
                contribution_score=contrib,
                venue=venue,
                confidence=conf,
                extraction_source="regex"
            ))

    return results