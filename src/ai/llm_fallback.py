def call_ollama_gpa_transcript(text: str,
                                timeout: int = 120) -> dict:
    """
    Extraction GPA spécialisée pour les transcripts.
    Plus fiable que regex sur les tableaux de notes.
    """
    prompt = (
        "You are an academic transcript parser.\n"
        "Find the FINAL CUMULATIVE GPA in the transcript.\n\n"
        "IMPORTANT RULES:\n"
        "- GPA scale is almost always 4.0 unless explicitly stated\n"
        "- Numbers like 114, 30, 45 are CREDITS not GPA scale\n"
        "- Look for: GPA: 3.80 or CGPA: 3.5/4.0 or TOTAL ... 3.80\n"
        "- If you see 'GPA: 3.80' with no scale → scale = 4.0\n\n"
        "Return ONLY valid JSON:\n"
        '{"gpa_raw": <number>, "gpa_scale": <4.0 default>, '
        '"gpa_normalized_4": <value>, "confidence": <0-1>, '
        '"evidence": "<exact line>"}\n\n'
        f"Transcript:\n{text[:2000]}\n\nJSON:"
    )
    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt,
                  "stream": False,
                  "options": {"temperature": 0.1}},
            timeout=timeout
        )
        raw = r.json().get("response", "").strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(m.group(0)) if m else {}
        # Validation post-LLM
        return _validate_gpa_result(result)
    except Exception:
        return {}


def _validate_gpa_result(result: dict) -> dict:
    """Corrige les erreurs communes du LLM sur les GPA."""
    if not result:
        return result
    gpa_raw   = result.get("gpa_raw")
    gpa_scale = result.get("gpa_scale")
    if gpa_raw and gpa_scale and gpa_scale > 10 and gpa_raw <= 4.0:
        result["gpa_scale"]           = 4.0
        result["gpa_normalized_4"]    = round(gpa_raw, 3)
        result["correction_applied"]  = True
    return result
