import requests
import os
import streamlit as st
from typing import List, Dict, Any, Optional, Tuple

# URL pour la communication entre conteneurs Docker (Interne)
API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000/api/v1")

# URL pour le navigateur de l'utilisateur (Externe - utilisé pour l'Iframe PDF et les téléchargements)
# Sur votre machine locale, c'est localhost. En production, ce sera l'IP du serveur.
EXTERNAL_API_BASE_URL = "http://localhost:8000/api/v1"

# --- 1. AUTHENTIFICATION ---

def login_user(email, password) -> Tuple[int, Dict]:
    """Authentifie l'utilisateur et récupère le token JWT."""
    url = f"{API_BASE_URL}/auth/login"
    data = {"username": email, "password": password}
    try:
        response = requests.post(url, data=data, timeout=10)
        return response.status_code, response.json()
    except Exception as e:
        return 503, {"detail": f"Backend unreachable: {str(e)}"}

# --- 2. GESTION DES SESSIONS ---

def get_sessions(token: str) -> List[Dict]:
    """Récupère toutes les sessions d'admission."""
    url = f"{API_BASE_URL}/sessions"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else []
    except:
        return []

# --- 3. UPLOAD ET INGESTION ---

def upload_paired_documents(session_id: str, cv_file, tr_file, token: str) -> Tuple[int, Dict]:
    """Envoie une paire de fichiers pour un candidat au pipeline d'IA."""
    url = f"{API_BASE_URL}/upload"
    params = {"session_id": session_id}
    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "cv": (cv_file.name, cv_file.getvalue(), cv_file.type),
        "transcript": (tr_file.name, tr_file.getvalue(), tr_file.type)
    }
    try:
        # Timeout long car l'upload de gros PDF peut prendre du temps
        response = requests.post(url, params=params, headers=headers, files=files, timeout=60)
        return response.status_code, response.json()
    except Exception as e:
        return 500, {"detail": str(e)}

# --- 4. CONSULTATION DES CANDIDATS ---

def get_applicants(session_id: str, token: str) -> Tuple[int, List]:
    """Récupère la liste simplifiée des candidats pour le Dashboard."""
    url = f"{API_BASE_URL}/applicants"
    params = {"session_id": session_id}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        return response.status_code, response.json()
    except:
        return 500, []

def get_applicant_detail(applicant_id: str, token: str) -> Optional[Dict]:
    """Récupère le profil complet (métriques + publications) d'un candidat."""
    url = f"{API_BASE_URL}/applicants/{applicant_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def get_multiple_applicants(applicant_ids: List[str], token: str) -> List[Dict]:
    """Récupère une liste de détails candidats (utile pour la comparaison)."""
    results = []
    for app_id in applicant_ids:
        data = get_applicant_detail(app_id, token)
        if data:
            results.append(data)
    return results

# --- 5. CORRECTIONS MANUELLES ---

def update_applicant_metrics(applicant_id: str, metrics_dict: Dict, token: str) -> bool:
    """Sauvegarde les corrections apportées manuellement par l'évaluateur."""
    url = f"{API_BASE_URL}/applicants/{applicant_id}/metrics"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.patch(url, json=metrics_dict, headers=headers, timeout=10)
        return response.status_code == 200
    except:
        return False

# --- 6. MOTEUR DE CLASSEMENT (RANKING) ---

def create_ranking_config(session_id: str, name: str, weights: Dict, token: str) -> Optional[Dict]:
    """Enregistre un nouveau profil de pondération (coefficients)."""
    url = f"{API_BASE_URL}/sessions/{session_id}/configs"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": name,
        "weights": weights,
        "tiebreak_field": "bsc_gpa_normalised"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def trigger_ranking_computation(session_id: str, config_id: str, token: str) -> Tuple[int, Optional[Dict]]:
    """Déclenche le calcul réel du score et du rang pour tous les candidats."""
    url = f"{API_BASE_URL}/ranking"
    params = {"session_id": session_id, "config_id": config_id}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(url, params=params, headers=headers, timeout=30)
        return response.status_code, response.json()
    except:
        return 500, None

def get_latest_ranking_results(session_id: str, token: str) -> Optional[Dict]:
    """Récupère le dernier snapshot de classement calculé."""
    url = f"{API_BASE_URL}/ranking/latest"
    params = {"session_id": session_id}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

# --- 7. AUDIT ET EXPORTS ---

def get_audit_logs(session_id: str, token: str) -> List[Dict]:
    """Récupère l'historique complet des actions effectuées sur une session."""
    url = f"{API_BASE_URL}/audit"
    params = {"session_id": session_id}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else []
    except:
        return []

def get_export_url(session_id: str) -> str:
    """Génère l'URL de téléchargement direct du fichier Excel (Browser-side)."""
    return f"{EXTERNAL_API_BASE_URL}/ranking/{session_id}/export"