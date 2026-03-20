from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class ExtractionResult:
    value: Optional[Any]
    confidence: float
    raw_match: Optional[str] = None
    source: str = "nlp"

class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, text: str) -> ExtractionResult:
        pass