import re
from dataclasses import dataclass, field
from typing import Optional


# Mapping pour normaliser les noms de sections variantes
SECTION_ALIASES = {
    "EDUCATION":    ["education", "academic background", "academic qualifications",
                     "academic history", "degrees"],
    "PUBLICATIONS": ["publication", "publications", "research publications",
                     "papers", "journal", "conference papers", "research output"],
    "EXPERIENCE":   ["experience", "work experience", "professional experience",
                     "employment", "employment history", "career"],
    "SKILLS":       ["skill", "skills", "skill highlights", "technical skills",
                     "core competencies", "competencies", "expertise"],
    "PROJECTS":     ["project", "projects", "academic projects", "research projects"],
    "SUMMARY":      ["summary", "profile", "about me", "objective",
                     "professional summary", "career objective"],
    "AWARDS":       ["award", "awards", "honors", "honours",
                     "achievements", "distinctions"],
    "CERTIFICATIONS": ["certification", "certifications", "certificates",
                       "professional development"],
}

# Construire les patterns depuis le mapping
def _build_patterns(aliases: dict) -> list:
    patterns = []
    for canonical, variants in aliases.items():
        escaped = [re.escape(v) for v in variants]
        pattern = r"^(" + "|".join(escaped) + r")[\s:]*$"
        patterns.append((canonical, pattern))
    return patterns

COMPILED_PATTERNS = [
    (canonical, re.compile(pattern, re.IGNORECASE))
    for canonical, pattern in _build_patterns(SECTION_ALIASES)
]


@dataclass
class SegmentationResult:
    sections: dict = field(default_factory=dict)
    detected_section_names: list = field(default_factory=list)
    confidence: float = 0.0
    warning: Optional[str] = None


def segment_document(text: str) -> SegmentationResult:
    """
    Segmente un texte de CV en sections nommées.

    Args:
        text: texte brut extrait par PyMuPDF ou Tesseract

    Returns:
        SegmentationResult avec sections dict + métadonnées
    """
    if not text or len(text.strip()) < 50:
        return SegmentationResult(
            sections={"HEADER": text},
            confidence=0.0,
            warning="Text too short — likely scanned PDF or empty document"
        )

    lines = text.split('\n')
    sections = {}
    current_section = "HEADER"
    current_lines = []

    for line in lines:
        line_stripped = line.strip()

        matched_canonical = None
        for canonical, pattern in COMPILED_PATTERNS:
            if pattern.match(line_stripped):
                matched_canonical = canonical
                break

        if matched_canonical:
            if current_lines:
                cleaned = _clean_section_text('\n'.join(current_lines))
                if cleaned:
                    sections[current_section] = cleaned
            current_section = matched_canonical
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        cleaned = _clean_section_text('\n'.join(current_lines))
        if cleaned:
            sections[current_section] = cleaned

    confidence = _compute_confidence(sections)
    warning = None
    if confidence < 0.3:
        warning = "Low segmentation confidence — few sections detected"

    return SegmentationResult(
        sections=sections,
        detected_section_names=list(sections.keys()),
        confidence=confidence,
        warning=warning
    )


def _clean_section_text(text: str) -> str:
    """Supprime les lignes vides en début/fin et les espaces parasites."""
    lines = [line.rstrip() for line in text.split('\n')]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines)


def _compute_confidence(sections: dict) -> float:
    """
    Score de confiance basé sur les sections métier détectées.
    Max 1.0 si toutes les sections clés sont présentes.
    """
    key_sections = ["EDUCATION", "PUBLICATIONS", "EXPERIENCE"]
    bonus_sections = ["SKILLS", "SUMMARY", "PROJECTS"]

    found_key = sum(1 for s in key_sections if s in sections)
    found_bonus = sum(1 for s in bonus_sections if s in sections)

    score = (found_key / len(key_sections)) * 0.7
    score += (found_bonus / len(bonus_sections)) * 0.3
    return round(score, 2)