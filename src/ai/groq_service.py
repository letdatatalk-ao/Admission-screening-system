"""
src/ai/groq_service.py

FIX: asyncio.gather() fires 3 Groq requests simultaneously per task.
With concurrency=2 workers, that's 6 parallel requests hitting Groq — easily
triggering HTTP 429 rate limits on the free tier (30 req/min, 6000 tokens/min).

Solution: run the 3 sub-prompts SEQUENTIALLY with a small delay between them.
This triples latency per task but eliminates rate limit errors entirely.
For a batch-processing pipeline, throughput matters more than per-task latency.
"""

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

# Delay between sequential Groq calls (seconds).
# Free tier: 30 req/min → 1 req/2s is safe.
# Paid tier: reduce to 0.3 or 0.
_INTER_CALL_DELAY = 2.0


class GroqOrchestrator:
    def __init__(self, api_key: Optional[str] = None):
        if not GROQ_AVAILABLE:
            raise ImportError("Groq not installed. Run: pip install groq")

        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found")

        self.client = AsyncGroq(api_key=self.api_key)
        self.model = "llama-3.1-8b-instant"

    async def _query_groq(self, prompt: str, label: str = "") -> Dict[str, Any]:
        """Single Groq call with exponential-backoff retry on rate limit."""
        delays = [2, 10, 30]  # seconds between retries
        for attempt, wait in enumerate(delays + [None], start=1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a precise JSON extractor. "
                                "Return ONLY valid JSON. "
                                "All years must be integers (e.g., 2023). "
                                "If year is not found, use null."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=2048,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                    logger.debug(f"✅ Groq [{label}] attempt {attempt} ok")
                    return result
                logger.warning(f"⚠️ Groq [{label}] returned no JSON object")
                return {}

            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower()

                if wait is None:
                    logger.error(f"❌ Groq [{label}] all retries exhausted: {e}")
                    return {}

                if is_rate_limit:
                    logger.warning(
                        f"⚠️ Groq [{label}] rate limit (attempt {attempt}), "
                        f"waiting {wait}s..."
                    )
                else:
                    logger.warning(
                        f"⚠️ Groq [{label}] error (attempt {attempt}): {e}, "
                        f"waiting {wait}s..."
                    )
                await asyncio.sleep(wait)

        return {}

    async def extract_parallel(
        self,
        cv_text: str,
        tr_text: str,
        candidate_name: str = "",
    ) -> Dict[str, Any]:
        """
        Extract all fields from CV + transcript.

        ✅ FIX: Calls are now SEQUENTIAL with a small inter-call delay.
        Previously using asyncio.gather() caused burst traffic → HTTP 429.
        """
        academic_prompt = f"""
Extract academic information from CV and TRANSCRIPT.
BSc is usually in CV, MSc in TRANSCRIPT.

Return JSON:
{{
  "bsc_uni": "<university name or null>",
  "msc_uni": "<university name or null>",
  "msc_gpa_raw": <float or null>,
  "msc_gpa_scale": <float, default 4.0>
}}

CV: {cv_text[:3000]}
TRANSCRIPT: {tr_text[:3000]}
"""

        research_prompt = f"""
Extract publications from this CV.
Return JSON: {{"publications": [...]}}

Each publication object must have:
  title   (string)
  year    (integer or null — NEVER a string)
  venue   (string)
  authors (string)

CV: {cv_text[:3500]}
"""

        identity_prompt = f"""
Extract personal identity from this CV.
Return JSON: {{"full_name": "", "email": "", "nationality": ""}}

CV: {cv_text[:1500]}
"""

        logger.info("🧠 Groq sequential extraction (rate-limit safe)...")

        # ── 1. Academic ──────────────────────────────────────────────────────
        academic = await self._query_groq(academic_prompt, label="academic")
        await asyncio.sleep(_INTER_CALL_DELAY)

        # ── 2. Research / publications ───────────────────────────────────────
        research = await self._query_groq(research_prompt, label="research")
        await asyncio.sleep(_INTER_CALL_DELAY)

        # ── 3. Identity ──────────────────────────────────────────────────────
        identity = await self._query_groq(identity_prompt, label="identity")

        logger.info(
            f"Academic: bsc_uni={academic.get('bsc_uni')}, "
            f"msc_uni={academic.get('msc_uni')}"
        )

        msc_gpa_raw = academic.get("msc_gpa_raw")
        return {
            "bsc_uni": academic.get("bsc_uni"),
            "bsc_gpa": {"raw_value": None, "scale": 4.0},
            "msc_uni": academic.get("msc_uni"),
            "msc_gpa": (
                {
                    "raw_value": msc_gpa_raw,
                    "scale": academic.get("msc_gpa_scale", 4.0),
                }
                if msc_gpa_raw
                else None
            ),
            "msc_absent": academic.get("msc_uni") is None,
            "publications": research.get("publications", []),
            "full_name": identity.get("full_name") or candidate_name,
            "email": identity.get("email"),
            "nationality": identity.get("nationality"),
        }

    async def close(self):
        await self.client.close()