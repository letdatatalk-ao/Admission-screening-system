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
        # cv_education/cv_publications/cv_experience are pre-segmented CV section
        # chunks (see DocumentSegmenter). Prefer them over blind head-of-document
        # slices — same fix applied to the Groq/Anthropic orchestrators.
        edu_block = cv_education if len(cv_education.strip()) >= 100 else cv_text[:2000]
        exp_block = cv_experience if len(cv_experience.strip()) >= 40 else ""
        pub_block = cv_publications if len(cv_publications.strip()) >= 100 else cv_text[:3000]

        # ✅ PROMPT ACADÉMIQUE CORRIGÉ : BSc dans CV, MSc dans transcript
        academic_prompt = f"""
You are an academic transcript and CV parser. Extract Bachelor (BSc), Master (MSc)
and PhD degrees, plus test scores and work experience.

IMPORTANT SOURCES:
- BSc (Bachelor) information is in the CV (Education section)
- MSc/PhD information may be in the CV Education section AND/OR the TRANSCRIPT

Return ONLY a JSON object with these exact keys:
{{
  "bsc_uni": "Bachelor university name or null",
  "bsc_country": "country or null",
  "bsc_field": "major or null",
  "bsc_year": null,
  "bsc_gpa_raw": null,
  "bsc_gpa_scale": 4.0,
  "msc_uni": "Master university name or null",
  "msc_country": "country or null",
  "msc_field": "major or null",
  "msc_year": null,
  "msc_gpa_raw": null,
  "msc_gpa_scale": 4.0,
  "phd_uni": "PhD university name or null",
  "phd_field": "topic or null",
  "phd_year": null,
  "gre_verbal": null,
  "gre_quant": null,
  "gre_awa": null,
  "ielts_score": null,
  "toefl_score": null,
  "work_exp_years": null
}}

RULES:
- Look for "Bachelor of Science", "BSc", "Bachelor's degree", "Licence" for BSc.
- Look for "Master of Science", "MSc", "Master's degree" for MSc.
- Look for "PhD", "Doctorate", "Doctor of Philosophy" for PhD.
- msc_gpa_scale / bsc_gpa_scale: the denominator (e.g., 3.5/4.0 -> scale=4.0; 14/20 -> scale=20.0)
- Cumulative GPA is usually near the end of the transcript.
- work_exp_years: sum non-student professional roles only (see EXPERIENCE section); 6 months = 0.5.
- If a field is genuinely absent, use null — do not guess.

--- CV (Education section for BSc/MSc) ---
{edu_block[:2000]}

--- CV (Professional Experience section) ---
{exp_block[:1200]}

--- TRANSCRIPT (for MSc/PhD GPA) ---
{tr_text[:3000]}
"""

        research_prompt = f"""
Extract publications, research interests and awards from this CV.
Return ONLY a JSON object:
{{"publications": [], "research_interests": [], "awards": []}}
Each publication should have: title, authors, year, venue, pub_type
(journal|conference|book_chapter|preprint|thesis), author_position, total_authors, under_review.

CV:
{pub_block[:3000]}
"""

        identity_prompt = f"""
Extract the candidate identity from this CV header.
Return ONLY a JSON object: {{"full_name": "", "email": "", "nationality": "", "phone": "", "linkedin": ""}}

CV:
{cv_text[:1500]}
"""

        logger.info("Parallel agents: %s (Acad) & %s (Pubs) & %s (Ident)...",
                    self.models["academic"], self.models["research"], self.models["identity"])

        # Lancement parallèle
        results = await asyncio.gather(
            self._query_agent(self.models["academic"], academic_prompt),
            self._query_agent(self.models["research"], research_prompt),
            self._query_agent(self.models["identity"], identity_prompt),
        )

        academic, research, identity = results

        if not academic and not research and not identity:
            # All three agents failed (Ollama unreachable, timeout, or bad output on
            # every one) — raise so the pipeline records a real retry/failure instead
            # of silently saving an applicant with every field blank.
            raise RuntimeError("Ollama: all three extraction agents returned empty results")

        # Log pour débogage
        logger.info(f"Academic extraction result: bsc_uni={academic.get('bsc_uni')}, msc_uni={academic.get('msc_uni')}, msc_gpa={academic.get('msc_gpa_raw')}")
        logger.info(f"Publications found: {len(research.get('publications', []))}")

        # --- FUSION SÉCURISÉE ---
        return {
            "bsc_uni":     academic.get("bsc_uni"),
            "bsc_country": academic.get("bsc_country"),
            "bsc_field":   academic.get("bsc_field"),
            "bsc_year":    academic.get("bsc_year"),
            "bsc_gpa":  {
                "raw_value": academic.get("bsc_gpa_raw"),
                "scale":     academic.get("bsc_gpa_scale", 4.0)
            },
            "msc_uni":     academic.get("msc_uni"),
            "msc_country": academic.get("msc_country"),
            "msc_field":   academic.get("msc_field"),
            "msc_year":    academic.get("msc_year"),
            "msc_gpa":  {
                "raw_value": academic.get("msc_gpa_raw"),
                "scale":     academic.get("msc_gpa_scale", 4.0)
            } if academic.get("msc_gpa_raw") is not None else None,
            "msc_absent":   academic.get("msc_uni") is None,
            "phd_uni":      academic.get("phd_uni"),
            "phd_field":    academic.get("phd_field"),
            "phd_year":     academic.get("phd_year"),
            "gre_verbal":   academic.get("gre_verbal"),
            "gre_quant":    academic.get("gre_quant"),
            "gre_awa":      academic.get("gre_awa"),
            "ielts_score":  academic.get("ielts_score"),
            "toefl_score":  academic.get("toefl_score"),
            "work_exp_years": academic.get("work_exp_years"),
            "publications":       research.get("publications", []),
            "research_interests": research.get("research_interests", []),
            "awards":              research.get("awards", []),
            "full_name":    identity.get("full_name") or candidate_name,
            "email":        identity.get("email"),
            "nationality":  identity.get("nationality"),
            "phone":        identity.get("phone"),
            "linkedin":     identity.get("linkedin"),
        }

    async def close(self):
        """Ferme le client HTTP."""
        await self.client.aclose()