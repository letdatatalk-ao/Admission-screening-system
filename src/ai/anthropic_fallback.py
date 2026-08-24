"""
src/ai/anthropic_fallback.py

Anthropic fallback orchestrator using httpx (no SDK required).
Activates automatically when all Groq keys are exhausted.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict

import httpx

from src.ai.groq_service import (
    _SYS_PROMPT,
    _assemble_extraction_results,
    _build_academic_context,
    _build_research_context,
    _prompt_academic_identity,
    _prompt_research,
)
from src.preprocessing.sanitizer import sanitize_for_prompt  # noqa: F401 (re-exported via groq_service)

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicOrchestrator:
    """
    Fallback orchestrator backed by Anthropic's API.
    Uses claude-haiku-4-5-20251001 for cost/speed parity with Groq.
    Implements the same extract_parallel interface as GroqOrchestrator.
    """

    def __init__(self):
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.model = os.getenv("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5-20251001")
        logger.info(f"AnthropicOrchestrator ready — model={self.model}")

    async def _call(
        self,
        prompt: str,
        label: str,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": _SYS_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(_API_URL, headers=headers, json=body)
                    resp.raise_for_status()
                    text = resp.json()["content"][0]["text"]
                    m = re.search(r"\{.*\}", text, re.DOTALL)
                    if m:
                        logger.debug(f"[{label}] Anthropic call succeeded")
                        return json.loads(m.group(0))
                    logger.warning(f"[{label}] No JSON in Anthropic response (attempt {attempt + 1})")
                    if attempt < 2:
                        continue
                    raise RuntimeError(f"[{label}] Anthropic returned no parseable JSON after {attempt + 1} attempts")

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (529, 503) and attempt < 2:   # overloaded — backoff
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                if status == 401:
                    raise RuntimeError("Anthropic API key invalid (401)")
                logger.error(f"[{label}] Anthropic HTTP {status}: {e}")
                raise RuntimeError(f"[{label}] Anthropic HTTP {status}") from e

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < 2:
                    await asyncio.sleep(5)
                    continue
                logger.error(f"[{label}] Anthropic network error: {e}")
                raise RuntimeError(f"[{label}] Anthropic network error: {e}") from e

        raise RuntimeError(f"[{label}] Anthropic call exhausted all retries")

    async def extract_parallel(
        self,
        cv_text: str,
        tr_text: str,
        candidate_name: str = "",
        cv_education: str = "",
        cv_publications: str = "",
        cv_experience: str = "",
        cv_language: str = "english",
    ) -> Dict[str, Any]:
        cv_block, tr_block = _build_academic_context(cv_text, tr_text, cv_education, cv_experience)
        res_block = _build_research_context(cv_text, cv_publications)

        acad = await self._call(
            _prompt_academic_identity(cv_block, tr_block, cv_language),
            label="anthropic:academic+id",
            max_tokens=1024,
        )
        await asyncio.sleep(1.0)

        extracted_name = acad.get("full_name") or candidate_name

        res = await self._call(
            _prompt_research(res_block, extracted_name, cv_language),
            label="anthropic:research",
            max_tokens=2048,
        )

        logger.info(
            f"[Anthropic] bsc={acad.get('bsc_uni')!r} "
            f"msc={acad.get('msc_uni')!r} "
            f"pubs={len(res.get('publications', []))}"
        )
        return _assemble_extraction_results(acad, res)

    async def close(self):
        pass
