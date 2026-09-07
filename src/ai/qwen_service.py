"""
src/ai/qwen_service.py

Qwen extraction orchestrator (via Scaleway Generative APIs, OpenAI-compatible).
Same 2-call-per-applicant shape as GroqOrchestrator, reusing its prompt and
context builders — only the transport and the model's reasoning behaviour differ.

qwen3.6-35b-a3b is a reasoning model: it emits a hidden "reasoning" trace before
the actual answer (returned in message.model_extra["reasoning"], separate from
message.content) that consumes real completion tokens. A trivial 3-field JSON
extraction burned ~900 completion tokens in testing, almost all of it reasoning —
so max_tokens has to budget for the trace, not just the JSON output, or the
response gets cut off before message.content is ever written.
"""

import asyncio
import json
import logging
import re
import os
import time
from typing import Dict, Any

from src.monitoring.metrics import LLM_CALLS, LLM_CALL_DURATION
from src.ai.groq_service import (
    _build_academic_context,
    _build_research_context,
    _prompt_academic_identity,
    _prompt_research,
    _assemble_extraction_results,
    _SYS_PROMPT,
)

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("openai package not installed — pip install openai")

_DEFAULT_MODEL = "qwen3.6-35b-a3b"


class QwenOrchestrator:
    def __init__(self):
        if not OPENAI_SDK_AVAILABLE:
            raise ImportError("openai not installed — pip install openai")
        api_key  = os.getenv("SCALEWAY_API_KEY", "").strip()
        base_url = os.getenv("SCALEWAY_BASE_URL", "").strip()
        if not api_key or not base_url:
            raise ValueError(
                "Set SCALEWAY_API_KEY and SCALEWAY_BASE_URL to use the Qwen provider."
            )
        self.model = os.getenv("QWEN_MODEL", _DEFAULT_MODEL)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"QwenOrchestrator ready — model={self.model}")

    async def _call(
        self,
        prompt: str,
        label: str,
        max_tokens: int = 3500,
    ) -> Dict[str, Any]:
        for attempt in range(4):
            _t0 = time.monotonic()
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _SYS_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    reasoning_effort="low",
                )
                raw = resp.choices[0].message.content or ""
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    result = json.loads(m.group(0))
                    elapsed = time.monotonic() - _t0
                    used = getattr(resp, "usage", None)
                    if used:
                        logger.debug(
                            f"[{label}] in={used.prompt_tokens} out={used.completion_tokens}"
                        )
                    LLM_CALLS.labels(provider="qwen", label=label, status="success").inc()
                    LLM_CALL_DURATION.labels(provider="qwen", label=label).observe(elapsed)
                    return result

                # Empty content usually means the reasoning trace ate the whole
                # max_tokens budget before the model ever wrote the JSON answer.
                logger.warning(
                    f"[{label}] no JSON in response (try {attempt + 1}) — "
                    f"widening max_tokens ({max_tokens} → {int(max_tokens * 1.5)})"
                )
                LLM_CALLS.labels(provider="qwen", label=label, status="empty_response").inc()
                if attempt < 2:
                    max_tokens = int(max_tokens * 1.5)
                    continue
                raise RuntimeError(
                    f"[{label}] model returned no parseable JSON after {attempt + 1} attempts"
                )

            except Exception as e:
                LLM_CALLS.labels(provider="qwen", label=label, status="error").inc()
                if attempt < 2:
                    logger.warning(
                        f"[{label}] error (try {attempt + 1}): {str(e)[:150]} — retry in 5s"
                    )
                    await asyncio.sleep(5)
                    continue
                raise RuntimeError(f"Qwen [{label}] failed after {attempt + 1} attempts: {e}") from e

        raise RuntimeError(f"[{label}] exhausted retry budget")

    # ── Public extraction API ─────────────────────────────────────────────────

    async def extract_parallel(
        self,
        cv_text:         str,
        tr_text:         str,
        candidate_name:  str = "",
        cv_education:    str = "",
        cv_publications: str = "",
        cv_experience:   str = "",
        cv_language:     str = "english",
    ) -> Dict[str, Any]:
        cv_block, tr_block = _build_academic_context(cv_text, tr_text, cv_education, cv_experience)
        res_block = _build_research_context(cv_text, cv_publications)

        # Empirically calibrated against real CV/transcript prompts: the model's
        # reasoning trace alone regularly runs 3000-5000+ tokens before it writes
        # the JSON answer, so starting low and widening on retry (as qwen_service
        # did originally) doubled real latency on almost every call. Starting at
        # the level that actually worked in testing avoids that wasted round trip.
        acad = await self._call(
            _prompt_academic_identity(cv_block, tr_block, cv_language),
            label="academic+id",
            max_tokens=5500,
        )
        extracted_name = acad.get("full_name") or candidate_name

        res = await self._call(
            _prompt_research(res_block, extracted_name, cv_language),
            label="research",
            max_tokens=6500,
        )

        logger.info(
            f"Academic: bsc_uni={acad.get('bsc_uni')!r} "
            f"msc_uni={acad.get('msc_uni')!r} "
            f"phd={acad.get('phd_present')} "
            f"msc_gpa={acad.get('msc_gpa_raw')}/{acad.get('msc_gpa_scale')}"
        )
        logger.info(
            f"Research: pubs={len(res.get('publications', []))} "
            f"interests={len(res.get('research_interests', []))} "
            f"awards={len(res.get('awards', []))}"
        )

        return _assemble_extraction_results(acad, res)

    async def close(self):
        await self._client.close()
