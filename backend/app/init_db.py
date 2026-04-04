import asyncio
import sys
import os

# On s'assure que le dossier racine est dans le path
sys.path.append(os.getcwd())

from backend.app.db.database import engine
from backend.app.db.models import Base

async def init_models():
    print("⏳ Connexion à PostgreSQL et création des tables...")
    try:
        async with engine.begin() as conn:
            # Cette ligne crée toutes les tables définies dans models.py
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Base de données initialisée avec succès !")
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation : {e}")

if __name__ == "__main__":
    asyncio.run(init_models())