import sys
sys.path.insert(0, '/app/backend')
import asyncio
from app.db.database import engine
from app.db.models import Base, User
from passlib.context import CryptContext
import uuid
from sqlalchemy import text

async def setup():
    async with engine.begin() as conn:
        # Créer les tables
        await conn.run_sync(Base.metadata.create_all)
        print('✅ Tables créées')
        
        # Vérifier si l'admin existe
        result = await conn.execute(text('SELECT 1 FROM users WHERE email = :email'), {'email': 'admin@ku.ac.ae'})
        if not result.fetchone():
            pwd_context = CryptContext(schemes=['bcrypt'])
            user_id = str(uuid.uuid4())
            await conn.execute(
                text('INSERT INTO users (id, email, full_name, role, hashed_password, is_active) VALUES (:id, :email, :full_name, :role, :password, True)'),
                {'id': user_id, 'email': 'admin@ku.ac.ae', 'full_name': 'Administrateur', 'role': 'admin', 'password': pwd_context.hash('admin123')}
            )
            print('✅ Admin créé: admin@ku.ac.ae / admin123')
        else:
            print('✅ Admin existe déjà')

asyncio.run(setup())