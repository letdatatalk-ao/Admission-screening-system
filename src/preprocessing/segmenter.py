# src/preprocessing/segmenter.py

import re
from typing import Optional
from dataclasses import dataclass

@dataclass
class DocumentChunks:
    header:       str = ""
    education:    str = ""
    publications: str = ""
    experience:   str = ""
    others:       str = ""
    raw_text:     str = ""

class DocumentSegmenter:

    SECTION_PATTERNS = {
        "EDUCATION": r"""(?ix)\b(
            education | academic | qualifications | formation | scolarit[eé] |
            [eé]tudes | diplom | degrees? | studies | parcours\s+acad
        )\b""",

        "PUBLICATIONS": r"""(?ix)\b(
            publications? | research | papers? | journals? |
            conf[eé]rence | proceedings | articles? | pr[eé]sentations? |
            communications? | posters?
        )\b""",

        "EXPERIENCE": r"""(?ix)\b(
            experience | employment | work\s+history | career | professional |
            exp[eé]rience | parcours\s+professionnel | postes? | positions?
        )\b""",

        "SKILLS": r"""(?ix)\b(
            skills? | comp[eé]tences? | languages? | tools? | technologies |
            technical | outils | logiciels?
        )\b""",

        "AWARDS": r"""(?ix)\b(
            awards? | honors? | honours? | distinctions? | prizes? |
            r[eé]compenses? | prix | achievements?
        )\b""",
    }

    def _is_section_header(self, line: str) -> Optional[str]:
        stripped = line.strip()
        if not stripped or len(stripped) > 50:
            return None

        alpha_chars = [c for c in stripped if c.isalpha()]
        if not alpha_chars:
            return None

        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)

        for sec, pattern in self.SECTION_PATTERNS.items():
            if re.search(pattern, stripped):
                if upper_ratio > 0.5 or len(stripped) < 30:
                    return sec
        return None

    def segment(self, text: str) -> DocumentChunks:
        chunks = DocumentChunks(raw_text=text)
        lines = text.split('\n')
        current_section = "HEADER"

        captured = {sec: [] for sec in self.SECTION_PATTERNS}
        captured["HEADER"] = []
        captured["OTHERS"] = []

        for line in lines:
            detected = self._is_section_header(line)
            if detected:
                current_section = detected
                continue

            target = captured.get(current_section, captured["OTHERS"])
            if line.strip():
                target.append(line.strip())

        chunks.header       = "\n".join(captured["HEADER"])
        chunks.education    = "\n".join(captured["EDUCATION"])
        chunks.publications = "\n".join(captured["PUBLICATIONS"])
        chunks.experience   = "\n".join(captured["EXPERIENCE"])
        chunks.others       = "\n".join(
            captured.get("SKILLS",  []) +
            captured.get("AWARDS",  []) +
            captured["OTHERS"]
        )

        return chunks