from src.ai.confidence import GlobalConfidenceReport

def fuse_results(report: GlobalConfidenceReport,
                 llm_result: dict) -> dict:
    final = {}
    for f in report.fields:
        if not f.needs_llm:
            final[f.field_name] = {
                "value": f.value, "source": "nlp",
                "confidence": f.confidence}
        elif f.field_name in llm_result and llm_result[f.field_name]:
            final[f.field_name] = {
                "value": llm_result[f.field_name],
                "source": "llm", "confidence": 0.65}
        else:
            final[f.field_name] = {
                "value": None, "source": "failed",
                "confidence": 0.0, "needs_review": True}
    return final
