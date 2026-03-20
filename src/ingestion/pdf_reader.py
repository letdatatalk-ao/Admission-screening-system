import fitz
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractionOutput:
    text: str
    document_type: str        # native_pdf | scanned_pdf | docx
    char_count: int
    page_count: int
    avg_chars_per_page: float
    needs_ocr: bool


class PDFReader:
    SCANNED_THRESHOLD = 200   # chars per page — below = scanned

    def detect_type(self, pdf_path: str) -> str:
        doc = fitz.open(pdf_path)
        total = sum(len(p.get_text()) for p in doc)
        avg = total / len(doc) if len(doc) > 0 else 0
        return "scanned_pdf" if avg < self.SCANNED_THRESHOLD else "native_pdf"

    def extract(self, pdf_path: str) -> ExtractionOutput:
        doc = fitz.open(pdf_path)
        doc_type = self.detect_type(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        total = len(text)
        avg = total / len(doc) if len(doc) > 0 else 0
        return ExtractionOutput(
            text=text,
            document_type=doc_type,
            char_count=total,
            page_count=len(doc),
            avg_chars_per_page=avg,
            needs_ocr=(doc_type == "scanned_pdf")
        )
    