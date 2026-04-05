import asyncio
import json
import logging
import re
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

try:
    from groq import AsyncGroq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq not installed. Run: pip install groq")


class GroqOrchestrator:
    def __init__(self, api_key: Optional[str] = None):
        if not GROQ_AVAILABLE:
            raise ImportError("Groq not installed. Run: pip install groq")
        
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found")
        
        self.client = AsyncGroq(api_key=self.api_key)
        self.model = "llama-3.1-8b-instant"

    async def _query_groq(self, prompt: str) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a precise JSON extractor. Return ONLY valid JSON. All years must be integers (e.g., 2023). If year is not found, use null."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=2048,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                return {}
            except Exception as e:
                logger.warning(f"Groq attempt {attempt+1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
        return {}

    async def extract_parallel(self, cv_text: str, tr_text: str, candidate_name: str = "") -> Dict[str, Any]:
        
        academic_prompt = f"""
Extract academic information from CV and TRANSCRIPT.
BSc in CV, MSc in TRANSCRIPT.

Return JSON: {{"bsc_uni": "", "msc_uni": "", "msc_gpa_raw": 0.0, "msc_gpa_scale": 4.0}}

CV: {cv_text[:3000]}
TRANSCRIPT: {tr_text[:3000]}
"""

        research_prompt = f"""
Extract publications from CV.
Return JSON: {{"publications": []}}
Each publication: title (string), year (integer or null), venue (string), authors (string)

IMPORTANT: year MUST be an integer (like 2023) or null. Never put text in year.

CV: {cv_text[:3500]}
"""

        identity_prompt = f"""
Extract identity from CV.
Return JSON: {{"full_name": "", "email": "", "nationality": ""}}

CV: {cv_text[:1500]}
"""

        logger.info("🧠 Groq parallel extraction (ultra fast)...")

        # ✅ CORRECTION : asyncio.gather au lieu de asyncio.gather_sequential_...
        academic, research, identity = await asyncio.gather(
            self._query_groq(academic_prompt),
            self._query_groq(research_prompt),
            self._query_groq(identity_prompt),
        )

        logger.info(f"Academic: bsc_uni={academic.get('bsc_uni')}, msc_uni={academic.get('msc_uni')}")

        return {
            "bsc_uni": academic.get("bsc_uni"),
            "bsc_gpa": {"raw_value": None, "scale": 4.0},
            "msc_uni": academic.get("msc_uni"),
            "msc_gpa": {"raw_value": academic.get("msc_gpa_raw"), "scale": academic.get("msc_gpa_scale", 4.0)} if academic.get("msc_gpa_raw") else None,
            "msc_absent": academic.get("msc_uni") is None,
            "publications": research.get("publications", []),
            "full_name": identity.get("full_name") or candidate_name,
            "email": identity.get("email"),
            "nationality": identity.get("nationality"),
        }

    async def close(self):
        await self.client.close()