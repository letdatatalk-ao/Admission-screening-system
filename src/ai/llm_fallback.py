import re
import json
import requests
from typing import List

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b-instruct"

def call_ollama(section_text: str,
                fields_needed: List[str],
                timeout: int = 120) -> dict:
    schema = {f: None for f in fields_needed}
    prompt = (
        "You are an academic CV parser. "
        "Extract ONLY what is explicitly written. "
        "Return ONLY valid JSON, no explanation.\n\n"
        f"Fields needed: {fields_needed}\n\n"
        f"Return format: {json.dumps(schema)}\n\n"
        f"Text:\n{section_text[:1200]}\n\nJSON:"
    )
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }, timeout=timeout)

        if r.status_code != 200:
            return {}
        raw = r.json().get("response", "").strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}