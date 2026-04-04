import asyncio
import json
import logging
import re
from typing import Dict, Any
import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"

class LLMOrchestrator:
    def __init__(self, base_url: str = OLLAMA_URL):
        self.base_url = base_url
        
        # --- CONFIGURATION DES AGENTS ---
        self.models = {
            "academic":  "llama3.1:latest", # CHANGE : Llama 3.1 est INDISPENSABLE pour NYU
            "research":  "mistral:latest",  # Mistral est excellent pour les publications
            "identity":  "phi3:mini"        # Phi-3 est parfait (rapide) pour le nom/email
        }
        
        # Client avec un timeout de 400s pour laisser le CPU finir le travail
        self.client = httpx.AsyncClient(timeout=400.0)

    async def _safe_json_load(self, raw: str) -> Dict[str, Any]:
        try:
            # Nettoyage agressif pour ne garder que le JSON
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {}
        except Exception:
            return {}

    async def _query_agent(self, model: str, prompt: str) -> Dict[str, Any]:
        payload = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 4096}
        }
        try:
            r = await self.client.post(self.base_url, json=payload)
            r.raise_for_status()
            raw_response = r.json().get("response", "{}")
            return await self._safe_json_load(raw_response)
        except Exception as e:
            logger.error(f"❌ Agent {model} error: {e}")
            return {}

    async def extract_parallel(self, cv_text: str, tr_text: str, candidate_name: str = "") -> Dict[str, Any]:
        
        # PROMPT ACADÉMIQUE : On simplifie pour aider Llama 3.1
        academic_prompt = f"""
        Extract academic info from TRANSCRIPT. Return JSON ONLY.
        Keys:  "msc_uni", "msc_gpa_raw", "msc_gpa_scale".
        Note: Cumulative GPA for MSc is near the end.
        TRANSCRIPT: {tr_text[:4000]}
        """

        research_prompt = f"Extract publications for {candidate_name} from CV. JSON: {{'publications': []}}. CV: {cv_text[:3000]}"
        identity_prompt = f"Extract profile. JSON: {{'full_name', 'email', 'nationality'}}. CV: {cv_text[:1500]}"

        logger.info(f"🧠 Parallel agents: Llama3.1 (Acad) & Mistral (Pubs) & Phi3 (Ident)...")

        # Lancement parallèle
        results = await asyncio.gather(
            self._query_agent(self.models["academic"], academic_prompt),
            self._query_agent(self.models["research"], research_prompt),
            self._query_agent(self.models["identity"], identity_prompt),
        )

        academic, research, identity = results

        # --- LOGIQUE DE FUSION SÉCURISÉE ---
        return {
            "bsc_uni":  academic.get("bsc_uni"),
            "bsc_gpa":  {
                "raw_value": academic.get("bsc_gpa_raw"),
                "scale":     academic.get("bsc_gpa_scale", 4.0)
            },
            "msc_uni":  academic.get("msc_uni"),
            "msc_gpa":  {
                "raw_value": academic.get("msc_gpa_raw"),
                "scale":     academic.get("msc_gpa_scale", 4.0)
            } if academic.get("msc_gpa_raw") is not None else None, # FIX: is not None
            "msc_absent":   academic.get("msc_uni") is None,
            "publications": research.get("publications", []),
            "full_name":    identity.get("full_name") or candidate_name,
            "email":        identity.get("email"),
            "nationality":  identity.get("nationality"),
        }

    async def close(self):
        await self.client.aclose()