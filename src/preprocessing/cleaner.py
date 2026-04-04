import re
import unicodedata

class DocumentCleaner:
    def __init__(self):
        self.noise_patterns = [
            # Filigranes répétitifs
            (r'(COPY\s*){2,}',                  ' '),
            (r'(VOID\s*){2,}',                  ' '),
            (r'(OFFICIAL\s*){2,}',              ' '),
            (r'(NEW YORK UNIVERSITY\s*){2,}',   'NYU '),
            # Ligatures PDF
            (r'ﬁ', 'fi'), (r'ﬀ', 'ff'), (r'ﬂ', 'fl'),
            # Numéros de page seuls sur une ligne
            (r'^\s*\d{1,3}\s*$',                ''),
            # Mise en page
            (r'\t+',                            ' '),
            (r' {2,}',                          ' '),
            (r'(\n\s*){3,}',                    '\n\n'),
            # Lignes purement décoratives
            (r'^[_\-\.\*\/=\s]+$',              ''),
            # Emails et URLs (bruit pour l'extraction académique)
            (r'http\S+',                        ' '),
        ]

    def clean(self, text: str) -> str:
        if not text:
            return ""

        # 1. Normalisation Unicode
        text = unicodedata.normalize('NFKC', text)

        # 2. Patterns bruit
        for pattern, replacement in self.noise_patterns:
            flags = re.IGNORECASE | re.MULTILINE
            text = re.sub(pattern, replacement, text, flags=flags)

        # 3. Filtrage ligne par ligne
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Ignorer les lignes trop courtes qui sont probablement des artefacts
            if len(line) < 3 and not line[0].isdigit():
                continue
            clean_lines.append(line)

        return '\n'.join(clean_lines)