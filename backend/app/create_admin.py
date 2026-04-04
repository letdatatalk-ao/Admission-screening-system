import asyncio
from backend.app.db.database import SessionLocal
from backend.app.db.models import User
import uuid
import hashlib

# On définit une fonction de hash simple juste pour le premier admin 
# si passlib continue de bloquer
def simple_hash(password):
    from backend.app.api.v1.auth import get_password_hash
    try:
        return get_password_hash(password)
    except:
        # Fallback de secours (peu sécurisé mais permet d'entrer dans l'app)
        # À NE PAS UTILISER EN PRODUCTION
        print("⚠️ Warning: Using fallback hash due to bcrypt bug")
        return f"sha256${hashlib.sha256(password.encode()).hexdigest()}"

async def create_first_admin():
    async with SessionLocal() as db:
        admin = User(
            id=uuid.uuid4(),
            email="admin@ku.ac.ae",
            full_name="Admin Khalifa University",
            role="admin",
            is_active=True,
            hashed_password=simple_hash("admin123")
        )
        db.add(admin)
        await db.commit()
        print("✅ Utilisateur Admin créé : admin@ku.ac.ae / admin123")

if __name__ == "__main__":
    asyncio.run(create_first_admin())