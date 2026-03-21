from dataclasses import dataclass, field
from typing import Optional, List

CONFIDENCE_THRESHOLD = 0.70

@dataclass
class FieldConfidence:
    field_name:  str
    value:       object
    confidence:  float
    needs_llm:   bool
    source:      str

@dataclass
class GlobalConfidenceReport:
    fields:       List[FieldConfidence]
    global_score: float
    fields_ok:    List[str]
    fields_llm:   List[str]
    trigger_llm:  bool

def compute_confidence_report(gpa_bsc, gpa_msc,
                               univ_bsc, univ_msc,
                               pubs,
                               threshold=CONFIDENCE_THRESHOLD):
    fields = [
        FieldConfidence("bsc_gpa", gpa_bsc.normalised_gpa,
                        gpa_bsc.confidence,
                        gpa_bsc.confidence < threshold, "nlp"),
        FieldConfidence("msc_gpa", gpa_msc.normalised_gpa,
                        gpa_msc.confidence,
                        gpa_msc.confidence < threshold, "nlp"),
        FieldConfidence("bsc_university", univ_bsc.detected_name,
                        univ_bsc.confidence,
                        univ_bsc.confidence < threshold, "nlp"),
        FieldConfidence("msc_university", univ_msc.detected_name,
                        univ_msc.confidence,
                        univ_msc.confidence < threshold, "nlp"),
    ]
    for i, pub in enumerate(pubs[:3]):
        fields.append(FieldConfidence(
            f"publication_{i+1}", pub.title,
            pub.confidence, pub.confidence < threshold, "nlp"))

    global_score = round(
        sum(f.confidence for f in fields) / len(fields), 3)
    fields_ok  = [f.field_name for f in fields if not f.needs_llm]
    fields_llm = [f.field_name for f in fields if f.needs_llm]

    return GlobalConfidenceReport(
        fields=fields, global_score=global_score,
        fields_ok=fields_ok, fields_llm=fields_llm,
        trigger_llm=len(fields_llm) > 0)