"""
Factory pour choisir entre Ollama (local) et Groq (cloud ultra rapide).
Configuration via variable d'environnement LLM_PROVIDER:
- "ollama" (défaut) ou "groq"
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_llm_orchestrator():
    """
    Retourne l'orchestrateur LLM approprié selon la configuration.
    
    Variables d'environnement:
    - LLM_PROVIDER: "ollama" (défaut) ou "groq"
    - GROQ_API_KEY: clé API Groq (requis pour groq)
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    
    if provider == "groq":
        try:
            from src.ai.groq_service import GroqOrchestrator
            orchestrator = GroqOrchestrator()
            logger.info("🚀 Using Groq orchestrator (ultra fast)")
            return orchestrator
        except Exception as e:
            logger.warning(f"Failed to initialize Groq: {e}. Falling back to Ollama.")
            from src.ai.llm_service import LLMOrchestrator
            return LLMOrchestrator()
    else:
        from src.ai.llm_service import LLMOrchestrator
        logger.info("🐢 Using Ollama orchestrator (local)")
        return LLMOrchestrator()