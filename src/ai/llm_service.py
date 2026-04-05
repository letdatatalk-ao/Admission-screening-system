import asyncio
import json
import logging
import re
from typing import Dict, Any
import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://ollama:11434/api/generate"

class LLMOrchestrator:
    def __init__(self, base_url: str = OLLAMA_URL):
        self.base_url = base_url
        
        # --- CONFIGURATION DES AGENTS ---
        self.models = {
            "academic":  "llama3.1:latest",
            "research":  "mistral:latest",
            "identity":  "phi3:mini"
        }
        
        # Client avec un timeout de 400s pour laisser le CPU finir le travail
        self.client = httpx.AsyncClient(timeout=400.0)

    async def _safe_json_load(self, raw: str) -> Dict[str, Any]:
        """Extrait le premier bloc JSON valide d'une réponse LLM."""
        try:
            # Nettoyage agressif pour ne garder que le JSON
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {}
        except Exception:
            return {}

    async def _query_agent(self, model: str, prompt: str) -> Dict[str, Any]:
        """Interroge un modèle Ollama avec retry."""
        payload = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 4096}
        }
        
        # Tentative avec retry
        for attempt in range(3):
            try:
                logger.debug(f"Querying {model} (attempt {attempt+1}/3)")
                r = await self.client.post(self.base_url, json=payload)
                r.raise_for_status()
                raw_response = r.json().get("response", "{}")
                return await self._safe_json_load(raw_response)
            except httpx.ConnectError as e:
                logger.warning(f"⚠️ Connexion Ollama échouée pour {model} (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    logger.error(f"❌ Ollama injoignable pour {model} après 3 tentatives")
                    return {}
            except httpx.TimeoutException as e:
                logger.warning(f"⚠️ Timeout pour {model} (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    logger.error(f"❌ Timeout pour {model} après 3 tentatives")
                    return {}
            except Exception as e:
                logger.error(f"❌ Agent {model} error: {e}")
                return {}
        return {}

    async def extract_parallel(self, cv_text: str, tr_text: str, candidate_name: str = "") -> Dict[str, Any]:
        
        # ✅ PROMPT ACADÉMIQUE CORRIGÉ : BSc dans CV, MSc dans transcript
        academic_prompt = f"""
You are an academic transcript and CV parser. Extract BOTH Bachelor (BSc) and Master (MSc) degrees.

IMPORTANT SOURCES:
- BSc (Bachelor) information is in the CV (Education section)
- MSc (Master) information is in the TRANSCRIPT

Return ONLY a JSON object with these exact keys:
{{
  "bsc_uni": "Bachelor university name or null",
  "bsc_gpa_raw": null,
  "bsc_gpa_scale": 4.0,
  "msc_uni": "Master university name or null",
  "msc_gpa_raw": 0.0,
  "msc_gpa_scale": 4.0
}}

RULES FOR BSc (from CV):
- Look for "Bachelor of Science", "BSc", "Bachelor's degree", "Licence"
- Extract the university name (e.g., "AlHosn University")
- GPA is usually not present in CV, so keep bsc_gpa_raw = null

RULES FOR MSc (from TRANSCRIPT):
- Look for "Master of Science", "MSc", "Master's degree"
- Extract the university name (e.g., "New York University")
- msc_gpa_scale: the denominator (e.g., 3.5/4.0 → scale=4.0; 14/20 → scale=20.0)
- Cumulative GPA is usually near the end of the transcript

If a degree is not found, use null for all its fields.

--- CV (Education section for BSc) ---
{cv_text[:2000]}

--- TRANSCRIPT (for MSc only) ---
{tr_text[:3000]}
"""

        research_prompt = f"""
Extract publications from this CV.
Return ONLY a JSON object: {{"publications": []}}
Each publication should have: title, authors, year, venue, author_position, total_authors

CV:
{cv_text[:3000]}
"""

        identity_prompt = f"""
Extract the candidate identity from this CV header.
Return ONLY a JSON object: {{"full_name": "", "email": "", "nationality": ""}}

CV:
{cv_text[:1500]}
"""

        logger.info(f"🧠 Parallel agents: Llama3.1 (Acad) & Mistral (Pubs) & Phi3 (Ident)...")

        # Lancement parallèle
        results = await asyncio.gather(
            self._query_agent(self.models["academic"], academic_prompt),
            self._query_agent(self.models["research"], research_prompt),
            self._query_agent(self.models["identity"], identity_prompt),
        )

        academic, research, identity = results

        # Log pour débogage
        logger.info(f"Academic extraction result: bsc_uni={academic.get('bsc_uni')}, msc_uni={academic.get('msc_uni')}, msc_gpa={academic.get('msc_gpa_raw')}")
        logger.info(f"Publications found: {len(research.get('publications', []))}")

        # --- FUSION SÉCURISÉE ---
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
            } if academic.get("msc_gpa_raw") is not None else None,
            "msc_absent":   academic.get("msc_uni") is None,
            "publications": research.get("publications", []),
            "full_name":    identity.get("full_name") or candidate_name,
            "email":        identity.get("email"),
            "nationality":  identity.get("nationality"),
        }

    async def close(self):
        """Ferme le client HTTP."""
        await self.client.aclose()