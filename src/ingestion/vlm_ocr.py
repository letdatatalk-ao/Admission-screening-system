"""
src/ingestion/vlm_ocr.py

VLM-based OCR for scanned PDFs and standalone images.
Uses Groq's llama-3.2-11b-vision-preview — same key pool already configured.

Designed to run inside asyncio.to_thread() (synchronous httpx, safe in a thread).
Never call directly from the async event loop.
"""
import base64
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# 11B is fast and cheap; swap to 90B for higher accuracy on very messy scans
_VLM_MODEL = os.getenv("VLM_OCR_MODEL", "llama-3.2-11b-vision-preview")

_PRIVACY_MODE = os.getenv("LLM_PRIVACY_MODE", "true").lower() in ("1", "true", "yes")

_OCR_PROMPT = (
    "Extract ALL text from this document page exactly as it appears. "
    "Preserve the reading order: for multi-column layouts go top-to-bottom within each column, "
    "left column first, then right column. "
    "Represent table rows with '|' separators between cells. "
    "Output ONLY the plain text — no explanations, no markdown fences, no added formatting."
)


def _groq_ocr_page(img_bytes: bytes, api_key: str, client: httpx.Client) -> str:
    b64 = base64.standard_b64encode(img_bytes).decode()
    resp = client.post(
        _GROQ_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _VLM_MODEL,
            "max_tokens": 2048,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": _OCR_PROMPT},
                ],
            }],
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


_MODEL_DEAD_SIGNALS = ("model_not_found", "does not exist", "decommissioned")


def extract_pages_vlm(page_images: list[bytes]) -> Optional[str]:
    """
    OCR a list of page PNG images using Groq's vision model.

    Returns extracted text, or None when:
    - LLM_PRIVACY_MODE is true
    - No Groq key is configured
    - The configured vision model is unavailable (fails fast, does not burn
      through every page x every key retrying a permanently-dead model ID —
      Groq periodically retires vision models, e.g. llama-3.2-*-vision-preview)
    - All keys/pages fail for other reasons

    Rotates through GROQ_API_KEYS pool on 429/401 errors, mirroring GroqOrchestrator behaviour.
    """
    if _PRIVACY_MODE:
        logger.debug("VLM OCR skipped — LLM_PRIVACY_MODE is on")
        return None
    if not page_images:
        return None

    keys_raw = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
    if not keys:
        logger.warning("VLM OCR: no Groq API key configured")
        return None

    for api_key in keys:
        try:
            with httpx.Client() as client:
                pages = []
                failed = 0
                for i, img_bytes in enumerate(page_images):
                    try:
                        text = _groq_ocr_page(img_bytes, api_key, client)
                        if text:
                            pages.append(f"[PAGE {i + 1}]\n{text}")
                    except httpx.HTTPStatusError as e:
                        body = e.response.text.lower() if e.response is not None else ""
                        if e.response.status_code in (429, 401):
                            raise  # rotate to next key
                        if any(sig in body for sig in _MODEL_DEAD_SIGNALS):
                            logger.warning(
                                f"VLM OCR model {_VLM_MODEL!r} unavailable — "
                                "aborting VLM OCR for this document (falling back to Tesseract)"
                            )
                            return None
                        logger.warning(f"VLM OCR page {i + 1}: HTTP {e.response.status_code}")
                        failed += 1
                    except Exception as page_err:
                        logger.warning(f"VLM OCR page {i + 1} failed: {page_err}")
                        failed += 1

                if pages:
                    logger.info(
                        f"VLM OCR: {len(pages)} pages extracted "
                        f"({failed} failed) via {_VLM_MODEL}"
                    )
                    return "\n".join(pages)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 401):
                logger.warning(
                    f"VLM OCR key {api_key[:8]}… rejected "
                    f"({e.response.status_code}) — trying next"
                )
                continue
            logger.warning(f"VLM OCR HTTP error: {e}")

        except Exception as e:
            logger.warning(f"VLM OCR failed: {e}")

    return None
