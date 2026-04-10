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
You are an academic transcript and CV parser. Extract BOTH Bachelor (BSc) and Master (MSc) degrees.

IMPORTANT SOURCES:
- BSc (Bachelor) information is in the CV (Education section)
- MSc (Master) information is in the TRANSCRIPT

Return ONLY a JSON object with these exact keys:
{{
  "bsc_uni": "<Bachelor university name or null>",
  "msc_uni": "<Master university name or null>",
  "msc_gpa_raw": <cumulative GPA as float, or null>,
  "msc_gpa_scale": <denominator as float, default 4.0>
}}

RULES FOR BSc (from CV only):
- Look for: "Bachelor of Science", "BSc", "Bachelor's degree", "Licence", "B.S."
- Extract the university name (e.g., "AlHosn University")
- Do NOT look for BSc in the transcript

RULES FOR MSc (from TRANSCRIPT only):
- Look for: "Master of Science", "MSc", "Master's degree", "M.S."
- Extract the university name (e.g., "New York University")
- msc_gpa_scale: the denominator (e.g., 3.5/4.0 → 4.0 ; 14/20 → 20.0)
- Cumulative GPA is usually near the end of the transcript
- Do NOT look for MSc in the CV

If a degree is not found, use null for all its fields.

--- CV (Education section — BSc source) ---
{cv_text[:3000]}

--- TRANSCRIPT (MSc source only) ---
{tr_text[:3000]}
"""

        research_prompt = f"""
You are a research publications extractor. Extract all academic publications from this CV.

Return ONLY a JSON object with this exact structure:
{{"publications": []}}

Each publication object must have:
  "title"          : full title as a string
  "year"           : publication year as an INTEGER (e.g., 2023) — NEVER a string, null if not found
  "venue"          : journal or conference name as a string
  "authors"        : full authors string as listed
  "author_position": integer position of the candidate in the author list (1 = first author)
  "total_authors"  : total number of authors as integer

RULES:
- Look in sections named: "Publications", "Research", "Papers", "Journal Articles", "Conference Papers"
- If the section is absent or empty, return {{"publications": []}}
- Never invent or guess publications not explicitly listed

--- CV ---
{cv_text[:3500]}
"""

        identity_prompt = f"""
You are a CV identity extractor. Extract the candidate's personal information from the CV header.

Return ONLY a JSON object with these exact keys:
{{
  "full_name"  : "First and last name as written, or empty string",
  "email"      : "email address or empty string",
  "nationality": "nationality or country of origin if mentioned, or empty string"
}}

RULES:
- full_name: look at the very top of the CV (name is usually the largest text)
- email: look for @ symbol
- nationality: look for "Nationality:", "Citizen of", or country mentions in the header

--- CV ---
{cv_text[:1500]}
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