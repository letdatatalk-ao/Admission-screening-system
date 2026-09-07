"""
src/ai/llm_factory.py

Returns a FallbackOrchestrator that tries providers in priority order:
  1. Qwen        (Scaleway, primary — no daily quota ceiling like Groq's free tier)
  2. Groq         (fast, cheap — secondary; still useful as a fallback while its keys last)
  3. Anthropic    (reliable, higher quality — tertiary)
  4. Ollama       (local, no network — last resort)

Each provider must implement extract_parallel(**kwargs) and close().
The next provider is tried only when the current one raises RuntimeError
(typically "all API keys exhausted").
"""

import logging
import os

from src.monitoring.metrics import LLM_FALLBACKS

logger = logging.getLogger(__name__)

# When set, all cloud LLM providers (Qwen, Groq, Anthropic) are disabled.
# Only on-premise Ollama will be used — required for data residency compliance.
_PRIVACY_MODE = os.getenv("LLM_PRIVACY_MODE", "true").lower() in ("1", "true", "yes")


class FallbackOrchestrator:
    """
    Wraps an ordered list of LLM providers.
    On RuntimeError from a provider (keys exhausted / unreachable),
    automatically falls through to the next one.
    """

    def __init__(self, providers: list):
        if not providers:
            raise ValueError("FallbackOrchestrator requires at least one provider")
        self._providers = providers

    @property
    def model(self) -> str:
        return getattr(self._providers[0], "model", "unknown")

    # Signals that indicate a provider is temporarily unavailable — safe to try next
    _FALLTHROUGH_SIGNALS = (
        "exhausted", "unavailable", "overloaded",
        "503", "529", "rate limit", "quota",
    )

    async def extract_parallel(self, **kwargs) -> dict:
        last_err: Exception | None = None
        n = len(self._providers)

        for i, provider in enumerate(self._providers):
            try:
                return await provider.extract_parallel(**kwargs)

            except RuntimeError as e:
                # Explicit provider exhaustion — always fall through
                logger.warning(
                    f"{provider.__class__.__name__} exhausted ({e})"
                    f"{' — trying next' if i < n - 1 else ''}"
                )
                LLM_FALLBACKS.labels(from_provider=provider.__class__.__name__).inc()
                last_err = e

            except Exception as e:
                err_lower = str(e).lower()
                is_capacity = any(sig in err_lower for sig in self._FALLTHROUGH_SIGNALS)
                is_last = (i == n - 1)

                if is_capacity or not is_last:
                    # Capacity issue OR we still have fallback providers — try next
                    logger.warning(
                        f"{provider.__class__.__name__} error "
                        f"({'capacity' if is_capacity else 'unexpected'}): {e}"
                        f"{' — trying next' if not is_last else ''}"
                    )
                    LLM_FALLBACKS.labels(from_provider=provider.__class__.__name__).inc()
                    last_err = e
                else:
                    # Last provider, non-capacity error — propagate as-is
                    raise

        raise RuntimeError(f"All {n} LLM providers failed. Last error: {last_err}")

    async def close(self) -> None:
        for provider in self._providers:
            try:
                await provider.close()
            except Exception:
                pass


def get_llm_orchestrator():
    """
    Build and return the best available orchestrator.
    Registers providers in priority order based on env-var presence.
    """
    providers = []

    if _PRIVACY_MODE:
        logger.warning(
            "🔒 LLM_PRIVACY_MODE=true — Qwen, Groq and Anthropic disabled. "
            "All CV data is processed on-premise (Ollama only). "
            "Set LLM_PRIVACY_MODE=false to re-enable cloud providers."
        )

    # ── Qwen/Scaleway (primary: no daily-quota ceiling) — disabled in privacy mode
    if not _PRIVACY_MODE and os.getenv("SCALEWAY_API_KEY") and os.getenv("SCALEWAY_BASE_URL"):
        try:
            from src.ai.qwen_service import QwenOrchestrator
            providers.append(QwenOrchestrator())
            logger.info("✅ Qwen (Scaleway) registered as primary LLM")
        except Exception as e:
            logger.warning(f"Qwen init failed: {e}")

    # ── Groq (secondary: fast, free-tier quota) — disabled in privacy mode ───
    if not _PRIVACY_MODE and (os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEYS")):
        try:
            from src.ai.groq_service import GroqOrchestrator
            providers.append(GroqOrchestrator())
            logger.info("✅ Groq registered as secondary LLM")
        except Exception as e:
            logger.warning(f"Groq init failed: {e}")

    # ── Anthropic (tertiary: reliable, high quality) — disabled in privacy mode
    if not _PRIVACY_MODE and os.getenv("ANTHROPIC_API_KEY"):
        try:
            from src.ai.anthropic_fallback import AnthropicOrchestrator
            providers.append(AnthropicOrchestrator())
            logger.info("✅ Anthropic registered as tertiary LLM")
        except Exception as e:
            logger.warning(f"Anthropic init failed: {e}")

    # ── Ollama (on-premise: always attempted, primary in privacy mode) ────────
    try:
        from src.ai.llm_service import LLMOrchestrator
        providers.append(LLMOrchestrator())
        label = "primary (privacy mode)" if _PRIVACY_MODE else "last resort"
        logger.info(f"✅ Ollama registered as {label} LLM")
    except Exception as e:
        logger.warning(f"Ollama init failed: {e}")

    if not providers:
        raise RuntimeError(
            "No LLM provider available. "
            "Set SCALEWAY_API_KEY+SCALEWAY_BASE_URL, GROQ_API_KEY, ANTHROPIC_API_KEY, or run Ollama locally."
        )

    if len(providers) == 1:
        return providers[0]   # no wrapper overhead when only one provider

    return FallbackOrchestrator(providers)
