import os
import shutil
import hashlib
from pathlib import Path
from typing import Tuple

STORAGE_ROOT = Path("storage/raw")

def calculate_file_hash(file_content: bytes) -> str:
    """Calcule le SHA-256 pour détecter les doublons."""
    return hashlib.sha256(file_content).hexdigest()

def save_paired_documents(
    session_id: str, 
    applicant_id: str, 
    cv_file: bytes, 
    cv_filename: str,
    tr_file: bytes, 
    tr_filename: str
) -> Tuple[str, str, str, str]:
    """
    Sauvegarde physiquement la paire CV + Transcription.
    Retourne (cv_path, cv_hash, tr_path, tr_hash).
    """
    # Création du dossier : storage/raw/{session_id}/{applicant_id}/
    folder_path = STORAGE_ROOT / session_id / applicant_id
    folder_path.mkdir(parents=True, exist_ok=True)

    # Chemins finaux
    cv_dest = folder_path / f"cv_{cv_filename}"
    tr_dest = folder_path / f"tr_{tr_filename}"

    # Calcul des hashes
    cv_hash = calculate_file_hash(cv_file)
    tr_hash = calculate_file_hash(tr_file)

    # Écriture physique
    with cv_dest.open("wb") as f:
        f.write(cv_file)
    with tr_dest.open("wb") as f:
        f.write(tr_file)

    return str(cv_dest), cv_hash, str(tr_dest), tr_hash