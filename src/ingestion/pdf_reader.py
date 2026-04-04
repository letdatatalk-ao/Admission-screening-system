import fitz
import re
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RobustExtraction:
    content:    str
    doc_type:   str      # native | scanned
    page_count: int
    needs_ocr:  bool
    metadata:   dict


class PDFReader:
    # Seuil bas — certains transcripts ont peu de texte par page
    SCANNED_THRESHOLD = 50

    def __init__(self):
        # Chemin Tesseract dans le container Docker
        self._configure_tesseract()

    def _configure_tesseract(self):
        """Configure le chemin Tesseract selon l'environnement."""
        try:
            import pytesseract
            # Chemin Linux (container Docker)
            linux_path = "/usr/bin/tesseract"
            # Chemin Windows (développement local)
            windows_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

            if os.path.exists(linux_path):
                pytesseract.pytesseract.tesseract_cmd = linux_path
            elif os.path.exists(windows_path):
                pytesseract.pytesseract.tesseract_cmd = windows_path

            # Vérification silencieuse
            pytesseract.get_tesseract_version()
            self._ocr_available = True

        except Exception:
            self._ocr_available = False

    def _clean_ligatures(self, text: str) -> str:
        replacements = {
            'ﬁ': 'fi', 'ﬀ': 'ff', 'ﬂ': 'fl',
            'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st',
            '\x00': '', '\ufeff': '',
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    def _clean_noise(self, text: str) -> str:
        text = re.sub(r'(COPY\s*){3,}',                ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'(VOID\s*){3,}',                ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'(OFFICIAL\s*){2,}',            ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'(NEW YORK UNIVERSITY\s*){2,}', 'NYU ', text, flags=re.IGNORECASE)
        text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_native(self, doc) -> str:
        pages = []
        for page in doc:
            blocks = page.get_text("blocks", sort=True)
            page_text = "\n".join(
                b[4].strip() for b in blocks
                if isinstance(b[4], str) and b[4].strip()
            )
            pages.append(f"[PAGE {page.number + 1}]\n{page_text}")
        return "\n".join(pages)

    def _extract_with_ocr(self, pdf_path: str) -> str:
        if not self._ocr_available:
            # Fallback : fitz sans OCR
            doc = fitz.open(pdf_path)
            pages = []
            for page in doc:
                text = page.get_text("text").strip()
                if text:
                    pages.append(f"[PAGE {page.number + 1}]\n{text}")
            result = "\n".join(pages)
            return result if result.strip() else "[OCR_UNAVAILABLE]"

        import pytesseract
        from PIL import Image
        import io

        doc = fitz.open(pdf_path)
        pages = []
        for page in doc:
            # 300 DPI en niveaux de gris
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang='eng')
            if text.strip():
                pages.append(f"[PAGE {page.number + 1}]\n{text}")

        return "\n".join(pages)

    def extract(self, pdf_path: str) -> RobustExtraction:
        doc        = fitz.open(pdf_path)
        page_count = len(doc)

        total_chars = sum(
            len(page.get_text("text").strip()) for page in doc
        )
        avg_chars  = total_chars / max(page_count, 1)
        is_scanned = avg_chars < self.SCANNED_THRESHOLD

        if is_scanned:
            content = self._extract_with_ocr(pdf_path)
        else:
            content = self._extract_native(doc)
            content = self._clean_ligatures(content)

        content = self._clean_noise(content)

        meta = {
            "author":             doc.metadata.get("author", ""),
            "creator":            doc.metadata.get("creator", ""),
            "format":             "PDF",
            "avg_chars_per_page": round(avg_chars, 1),
            "ocr_used":           is_scanned,
            "ocr_available":      self._ocr_available,
        }

        return RobustExtraction(
            content=content,
            doc_type="scanned" if is_scanned else "native",
            page_count=page_count,
            needs_ocr=is_scanned,
            metadata=meta
        )