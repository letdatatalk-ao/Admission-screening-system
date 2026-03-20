import re
from dataclasses import dataclass
from typing import Optional


GPA_PATTERNS = [
    (r"(?:GPA|CGPA|Grade Point Average)[:\s]+(\d+\.?\d*)\s*/\s*(\d+\.?\d*)", "explicit_scale"),
    (r"(\d+\.?\d*)\s*/\s*(4\.0|4)", "scale_4"),
    (r"(\d+\.?\d*)\s*/\s*(5\.0|5)", "scale_5"),
    (r"(\d+\.?\d*)\s*/\s*(20)", "scale_20"),
    (r"(\d+\.?\d*)\s*/\s*(100)", "scale_100"),
    (r"(?:GPA|CGPA)[:\s]+(\d+\.?\d*)", "implicit_4"),
    (r"(?:cumulative|overall)\s+(?:GPA|average)[:\s]+(\d+\.?\d*)", "implicit_4"),
    (r"(Summa Cum Laude)", "honour"),
    (r"(Magna Cum Laude)", "honour"),
    (r"(Cum Laude)", "honour"),
]

HONOUR_MAP = {
    "summa cum laude": 3.9,
    "magna cum laude": 3.7,
    "cum laude":       3.5,
}


@dataclass
class GPAResult:
    raw_value: Optional[float]
    original_scale: Optional[float]
    normalised_gpa: Optional[float]
    confidence: float
    source: str
    raw_match: Optional[str]
    degree_level: str


def normalise_gpa(raw: float, scale: float) -> float:
    if scale == 4.0:   return round(raw, 3)
    elif scale == 5.0: return round(raw * 0.8, 3)
    elif scale == 20.0: return round(raw * 0.2, 3)
    elif scale == 100.0: return round(raw * 0.04, 3)
    else: return round(raw / scale * 4.0, 3)


def extract_gpa(text: str, degree_level: str = "unknown") -> GPAResult:
    if not text:
        return GPAResult(None, None, None, 0.0, "not_found", None, degree_level)

    for pattern, pattern_type in GPA_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if pattern_type == "honour":
                honour_text = match.group(1).lower()
                normalised = HONOUR_MAP.get(honour_text, 3.5)
                return GPAResult(normalised, 4.0, normalised, 0.60,
                                 "honour", match.group(0), degree_level)
            elif pattern_type == "explicit_scale":
                raw, scale = float(match.group(1)), float(match.group(2))
                return GPAResult(raw, scale, normalise_gpa(raw, scale), 0.95,
                                 "explicit_scale", match.group(0), degree_level)
            elif pattern_type in ("scale_4","scale_5","scale_20","scale_100"):
                raw, scale = float(match.group(1)), float(match.group(2))
                return GPAResult(raw, scale, normalise_gpa(raw, scale), 0.90,
                                 "explicit_scale", match.group(0), degree_level)
            elif pattern_type == "implicit_4":
                raw = float(match.group(1))
                return GPAResult(raw, 4.0, normalise_gpa(raw, 4.0), 0.75,
                                 "implicit_4", match.group(0), degree_level)

    return GPAResult(None, None, None, 0.0, "not_found", None, degree_level)