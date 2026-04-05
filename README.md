# KU Admission Screening System

Système automatisé et intelligent de screening des candidatures pour admission universitaire, utilisant l'IA pour l'extraction, l'enrichissement et l'analyse des CV et relevés de notes.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Status](https://img.shields.io/badge/status-production-brightgreen)

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture système](#architecture-système)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Documentation API](#documentation-api)
- [Dépannage](#dépannage)
- [Contribution](#contribution)
- [Support](#support)

---

## Vue d'ensemble

Le **KU Admission Screening System** est une plateforme complète conçue pour automatiser et optimiser le processus de sélection des candidats. Le système combine :

- **Extraction intelligente** de données depuis CV et transcripts
- **Enrichissement automatique** avec références académiques (QS, Scopus, CORE)
- **Analyse par IA** utilisant des modèles LLM locaux
- **Scoring et classement** basés sur des critères académiques
- **Interface intuitive** pour gestion et consultation des résultats

### Cas d'usage principaux

1. **Traitement en masse** : Upload groupé de CV et transcripts
2. **Extraction automatique** : Données académiques, expérience, compétences
3. **Enrichissement** : Rang des universités, revues et conférences
4. **Scoring intelligent** : Évaluation comparative des candidats
5. **Rapports** : Export et visualisation des résultats

---

## Architecture système

### Diagramme global

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (Streamlit)                        │
│        Interface web pour upload et visualisation               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend API (FastAPI)                        │
│          Endpoints REST pour gestion des candidats              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Task Queue (Celery + Redis)                        │
│          Traitement asynchrone des documents                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│              Pipeline IA (Python)                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │Extraction│→ │Nettoyage │→ │LLM/NLP   │→ │Fusion    │        │
│  │PDF/DOCX │  │texte     │  │Extraction│  │résultats │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Base de données (PostgreSQL)                       │
│      Stockage des candidats, métriques et publications          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│           Scoring & Ranking Engine                              │
│       Calcul des scores et classement des candidats             │
└─────────────────────────────────────────────────────────────────┘
```

### Stack technologique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **Backend** | FastAPI 0.104+ | API REST et orchestration |
| **Base de données** | PostgreSQL 16 | Stockage persistant |
| **File d'attente** | Redis 7.0 + Celery 5.4 | Traitement asynchrone |
| **Interface** | Streamlit 1.28+ | Application web |
| **LLM Local** | Ollama 0.18+ | Inférence locale |
| **Modèles** | Llama 3.1, Mistral, Phi-3 | Extraction et analyse |
| **ORM** | SQLAlchemy 2.0+ | Mappage objet-relationnel |
| **Matching** | RapidFuzz | Correspondance floue |

---

## Structure du projet

```
admission-screening-system/
│
├── backend/                          # Backend API et services
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/                   # Endpoints REST v1
│   │   │       ├── auth.py           # Authentification
│   │   │       ├── upload.py         # Upload documents
│   │   │       ├── applicants.py     # Gestion candidats
│   │   │       ├── ranking.py        # Classement
│   │   │       └── sessions.py       # Sessions évaluation
│   │   ├── db/
│   │   │   ├── models.py             # Modèles SQLAlchemy
│   │   │   ├── database.py           # Configuration DB
│   │   │   └── repositories/         # Accès aux données
│   │   ├── services/
│   │   │   ├── extraction.py         # Services extraction
│   │   │   ├── enrichment.py         # Enrichissement données
│   │   │   └── scoring.py            # Calcul scores
│   │   ├── tasks.py                  # Tâches Celery
│   │   ├── config.py                 # Configuration
│   │   └── main.py                   # Point d'entrée
│   ├── requirements.txt
│   └── Dockerfile
│
├── src/                              # Pipeline IA (coeur du système)
│   ├── pipeline/
│   │   └── screening_pipeline.py     # Orchestrateur principal
│   ├── ingestion/
│   │   ├── pdf_extractor.py          # Extraction PDF
│   │   └── docx_extractor.py         # Extraction DOCX
│   ├── preprocessing/
│   │   ├── text_cleaner.py           # Nettoyage texte
│   │   └── segmentation.py           # Segmentation documents
│   ├── extractors/
│   │   ├── academic_extractor.py     # Données académiques
│   │   ├── experience_extractor.py   # Expérience professionnelle
│   │   ├── qs_matcher.py             # Matching QS universités
│   │   ├── scopus_matcher.py         # Matching Scopus journaux
│   │   └── core_matcher.py           # Matching CORE conférences
│   ├── ai/
│   │   ├── ollama_service.py         # Client Ollama
│   │   ├── prompts.py                # Templates prompts
│   │   └── llm_extractor.py          # Extraction LLM
│   ├── models/
│   │   ├── candidate.py              # Modèle candidat
│   │   ├── metrics.py                # Modèles métriques
│   │   └── extraction.py             # Modèles extraction
│   └── scoring/
│       ├── normalizer.py             # Normalisation scores
│       ├── calculator.py             # Calcul scores
│       └── ranker.py                 # Classement candidats
│
├── data/                             # Fichiers de référence
│   ├── qs_rankings_2025.csv          # Classements QS (1504 universités)
│   ├── scimagojr_2024_computer_science.csv  # Scopus (2379 journaux)
│   └── core_conferences_2026.csv     # CORE (844 conférences)
│
├── streamlit_app/                    # Interface utilisateur
│   ├── app.py                        # Page principale
│   ├── config.py                     # Configuration Streamlit
│   └── pages/
│       ├── 01_Dashboard.py           # Tableau de bord
│       ├── 02_Upload.py              # Upload massif
│       ├── 03_Candidates.py          # Gestion candidats
│       ├── 04_Ranking.py             # Affichage classement
│       └── 05_Reports.py             # Rapports et exports
│
├── storage/                          # Stockage documents uploadés
├── logs/                             # Fichiers logs
│
├── docker-compose.yml                # Orchestration services
├── Dockerfile                        # Image Docker backend
├── requirements.txt                  # Dépendances Python
├── .env.example                      # Variables d'environnement
├── README.md                         # Cette documentation
└── LICENSE                           # Licence MIT
```

---

## Prérequis

### Système minimum

- **CPU** : 4 cœurs (8 recommandé)
- **RAM** : 8 GB (16 GB recommandé pour modèles LLM)
- **Disque** : 20 GB (pour Ollama et données)
- **Système d'exploitation** : Linux, macOS, Windows

### Logiciels requis

- **Docker** 20.10+ et **Docker Compose** 2.0+
  - [Installation Docker](https://docs.docker.com/get-docker/)
  
- **Python 3.12+** (pour développement local)
  - [Télécharger Python](https://www.python.org/downloads/)

---

## Installation

### Option 1 : Docker (Recommandée - Production)

La méthode Docker est recommandée pour l'environnement de production.

#### 1. Cloner le dépôt

```bash
git clone https://github.com/letdatatalk-ao/admission-screening-system.git
cd admission-screening-system
```

#### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos paramètres
nano .env
```

#### 3. Démarrer tous les services

```bash
docker-compose up -d
```

Cette commande démarre :
- PostgreSQL (base de données)
- Redis (cache et file d'attente)
- Ollama (moteur LLM)
- FastAPI (backend API)
- Celery Worker (traitement asynchrone)
- Streamlit (interface web)

#### 4. Vérifier le statut

```bash
docker-compose ps

# Résultat attendu :
# NAME                 STATUS
# postgres             Up (healthy)
# redis                Up (healthy)
# ollama               Up (healthy)
# backend              Up (healthy)
# celery_worker        Up (healthy)
# streamlit            Up (healthy)
```

#### 5. Initialiser la base de données

```bash
docker-compose exec backend python -c "
import asyncio
from app.db.database import engine, init_db

async def setup():
    await init_db()
    print('✓ Base de données initialisée')

asyncio.run(setup())
"
```

#### 6. Créer un utilisateur administrateur

```bash
docker-compose exec backend python -c "
import asyncio
from app.db.database import SessionLocal
from app.db.models import User
from passlib.context import CryptContext
import uuid

async def create_admin():
    async with SessionLocal() as db:
        pwd_context = CryptContext(schemes=['bcrypt'])
        admin = User(
            id=uuid.uuid4(),
            email='admin@ku.ac.ae',
            full_name='Administrateur',
            role='admin',
            hashed_password=pwd_context.hash('admin123')
        )
        db.add(admin)
        await db.commit()
        print('✓ Admin créé : admin@ku.ac.ae / admin123')

asyncio.run(create_admin())
"
```

#### 7. Télécharger les modèles Ollama

```bash
# Llama 3.1 (recommandé, ~8GB)
docker exec admission-ollama ollama pull llama3.1:latest

# Mistral (plus léger, ~7GB)
docker exec admission-ollama ollama pull mistral:latest

# Phi-3 Mini (très léger, ~2GB)
docker exec admission-ollama ollama pull phi3:mini
```

### Option 2 : Développement local

Pour le développement et les tests locaux.

#### 1. Créer un environnement virtuel

```bash
python3.12 -m venv venv

# Activer l'environnement
source venv/bin/activate      # Linux/macOS
# ou
venv\Scripts\activate          # Windows
```

#### 2. Installer les dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 3. Démarrer les services critiques

```bash
# Terminal 1 : PostgreSQL et Redis
docker-compose up -d postgres redis ollama

# Terminal 2 : FastAPI backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 3 : Celery worker
celery -A app.tasks worker --loglevel=info

# Terminal 4 : Streamlit frontend
cd streamlit_app
streamlit run app.py --server.port=8501
```

---

## Configuration

### Variables d'environnement (.env)

```bash
# === BASE DE DONNÉES ===
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/screening_db
DATABASE_ECHO=False

# === REDIS ===
REDIS_URL=redis://redis:6379/0

# === OLLAMA (LLM Local) ===
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=llama3.1:latest          # Modèle par défaut
OLLAMA_TEMPERATURE=0.3                # Température (0.0-1.0)
OLLAMA_TOP_P=0.9                      # Top-P sampling

# === AUTHENTIFICATION JWT ===
SECRET_KEY=your-very-secret-key-change-me-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# === UPLOAD FICHIERS ===
UPLOAD_DIR=./storage/uploads
MAX_FILE_SIZE_MB=50
ALLOWED_EXTENSIONS=pdf,docx

# === LOGGING ===
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log

# === ENVIRONNEMENT ===
ENVIRONMENT=production  # ou 'development'
DEBUG=False

# === DONNÉES DE RÉFÉRENCE ===
QS_RANKINGS_FILE=./data/qs_rankings_2025.csv
SCOPUS_RANKINGS_FILE=./data/scimagojr_2024_computer_science.csv
CORE_RANKINGS_FILE=./data/core_conferences_2026.csv
```

### Fichiers de référence

Les trois fichiers CSV de référence doivent être placés dans `./data/` :

#### 1. QS Rankings (qs_rankings_2025.csv)

```csv
rank,university_name,country
1,Massachusetts Institute of Technology,United States
2,Imperial College London,United Kingdom
3,University of Oxford,United Kingdom
...
```

**Source** : [QS World University Rankings 2025](https://www.topuniversities.com/)

#### 2. Scopus Rankings (scimagojr_2024_computer_science.csv)

```csv
journal_name,sjr_score,sjr_quartile,scopus_pct,issn
Foundations and Trends in Machine Learning,22.797,Q1,97.2,"19358245, 19358237"
Nature Biomedical Engineering,10.105,Q1,97.7,2157846X
...
```

**Source** : [SCImago Journal Rank](https://www.scimagojr.com/)

#### 3. CORE Rankings (core_conferences_2026.csv)

```csv
conference_name,acronym,core_rank,core_score
"ACM Conference on Applications, Technologies, Architectures, and Protocols for Computer Communication",SIGCOMM,A*,10
ACM Conference on Computer and Communications Security,CCS,A*,10
...
```

**Source** : [CORE Conference Portal](https://www.core.ac.uk/)

---

## Utilisation

### Accès aux services

| Service | URL | Identifiants |
|---------|-----|--------------|
| **Streamlit** (Interface web) | http://localhost:8501 | admin@ku.ac.ae / admin123 |
| **FastAPI** (API) | http://localhost:8000 | - |
| **Swagger** (Docs API) | http://localhost:8000/docs | - |
| **ReDoc** (Alternative) | http://localhost:8000/redoc | - |
| **PostgreSQL** | localhost:5432 | postgres / postgres |
| **Redis** | localhost:6379 | - |
| **Ollama** | http://localhost:11434 | - |

### Flux typique d'utilisation

#### 1. Authentification

1. Accédez à http://localhost:8501
2. Entrez vos identifiants (admin@ku.ac.ae / admin123)
3. Créez une nouvelle session d'évaluation

#### 2. Upload en masse

1. Allez à la page **Upload**
2. Sélectionnez la session cible
3. Déposez vos CV et Transcripts (format : `[ID] CV.pdf` et `[ID] T.pdf`)
4. Corrigez les paires incomplètes si nécessaire
5. Lancez le traitement

#### 3. Monitoring

1. Consultez le **Dashboard** pour voir la progression
2. Vérifiez les logs pour les détails du traitement

#### 4. Résultats

1. Allez à **Ranking** pour voir le classement
2. Consultez **Reports** pour les détails par candidat
3. Exportez les résultats en CSV ou PDF

---

## Documentation API

### Authentification

Tous les endpoints sauf `/auth/login` et `/health` nécessitent un token JWT.

#### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "admin@ku.ac.ae",
  "password": "admin123"
}
```

**Réponse (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### Upload de documents

#### Upload groupé

```http
POST /api/v1/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

- session_id: 550e8400-e29b-41d4-a716-446655440000
- cv: [fichier]
- transcript: [fichier]
```

### Gestion des candidats

#### Lister tous les candidats

```http
GET /api/v1/applicants
Authorization: Bearer {token}
```

**Réponse (200 OK):**

```json
{
  "total": 150,
  "page": 1,
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "first_name": "Ahmed",
      "last_name": "Ali",
      "email": "ahmed.ali@example.com",
      "status": "processed",
      "overall_score": 8.5
    }
  ]
}
```

#### Obtenir les détails d'un candidat

```http
GET /api/v1/applicants/{id}
Authorization: Bearer {token}
```

**Réponse (200 OK):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "first_name": "Ahmed",
  "last_name": "Ali",
  "email": "ahmed.ali@example.com",
  "education": {
    "degree": "Master of Science",
    "field": "Computer Science",
    "institution": "MIT",
    "graduation_year": 2023
  },
  "publications": [
    {
      "title": "Advanced ML Techniques",
      "journal": "Nature Machine Intelligence",
      "year": 2023,
      "scopus_quartile": "Q1"
    }
  ],
  "overall_score": 8.5,
  "rank": 12
}
```

#### Obtenir les métriques extraites

```http
GET /api/v1/applicants/{id}/metrics
Authorization: Bearer {token}
```

### Classement

#### Calculer le classement

```http
POST /api/v1/ranking/compute
Authorization: Bearer {token}
Content-Type: application/json

{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "criteria": {
    "education_weight": 0.3,
    "publications_weight": 0.4,
    "experience_weight": 0.3
  }
}
```

#### Obtenir le classement

```http
GET /api/v1/ranking/{session_id}?limit=100&offset=0
Authorization: Bearer {token}
```

**Réponse (200 OK):**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_candidates": 150,
  "candidates": [
    {
      "rank": 1,
      "first_name": "Fatima",
      "last_name": "Hassan",
      "score": 9.2,
      "education_score": 8.8,
      "publications_score": 9.5,
      "experience_score": 8.9
    }
  ]
}
```

### Sessions

#### Créer une session

```http
POST /api/v1/sessions
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Admission 2026 - Engineering",
  "description": "Screening pour programme Engineering",
  "criteria": {
    "min_gpa": 3.5,
    "required_experience_years": 0
  }
}
```

#### Lister les sessions

```http
GET /api/v1/sessions
Authorization: Bearer {token}
```

---

## Dépannage

### Problème : "Ollama connection refused"

**Cause** : Le service Ollama n'est pas accessible.

**Solution** :

```bash
# Vérifier l'état du conteneur
docker ps | grep ollama

# Redémarrer Ollama
docker-compose restart ollama

# Vérifier la connexion
curl http://localhost:11434/api/tags
```

### Problème : "Database relation does not exist"

**Cause** : La base de données n'est pas initialisée.

**Solution** :

```bash
# Réinitialiser complètement
docker-compose down -v
docker-compose up -d postgres redis ollama

# Attendre que PostgreSQL soit prêt
sleep 10

# Réinitialiser la BD
docker-compose exec backend python -c "from app.db.database import init_db; asyncio.run(init_db())"
```

### Problème : "Celery worker not responding"

**Cause** : Le worker Celery est arrêté ou n'a pas accès à Redis.

**Solution** :

```bash
# Voir les logs
docker-compose logs celery_worker

# Redémarrer le worker
docker-compose restart celery_worker

# Vérifier la connexion Redis
docker-compose exec redis redis-cli ping
# Doit retourner : PONG
```

### Problème : "Out of memory" (Ollama)

**Cause** : Le modèle LLM dépasse la capacité RAM.

**Solution** :

```bash
# Utiliser un modèle plus léger
# Remplacer dans .env :
OLLAMA_MODEL=phi3:mini

# Ou limiter la RAM pour Ollama
docker-compose down
# Éditer docker-compose.yml :
# services:
#   ollama:
#     environment:
#       - OLLAMA_NUM_PARALLEL=1
#       - OLLAMA_NUM_THREADS=2
docker-compose up -d ollama
```

### Logs et monitoring

```bash
# Voir tous les logs
docker-compose logs -f

# Logs d'un service spécifique
docker-compose logs -f backend
docker-compose logs -f celery_worker

# Voir les tâches Celery en cours
docker-compose exec celery_worker celery -A app.tasks inspect active
```

---



---

