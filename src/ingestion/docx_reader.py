from docx import Document
import os
from dataclasses import dataclass

@dataclass
class DocxExtraction:
    content: str
    page_count: int # Approximatif pour Word
    metadata: dict

class DocxReader:
    def extract(self, file_path: str) -> DocxExtraction:
        doc = Document(file_path)
        full_text = []

        # 1. Extraction des paragraphes
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text)

        # 2. Extraction des tableaux (Crucial pour les notes)
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                full_text.append(row_text)

        return DocxExtraction(
            content="\n".join(full_text),
            page_count=len(doc.sections), # Estimation
            metadata={"format": "DOCX"}
        )