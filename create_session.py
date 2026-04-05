import sys
sys.path.insert(0, '/app/backend')
import asyncio
from app.db.database import engine
from sqlalchemy import text
import uuid
from datetime import datetime

async def create_session():
    async with engine.begin() as conn:
        session_id = str(uuid.uuid4())
        await conn.execute(
            text('INSERT INTO evaluation_sessions (id, name, academic_year, qs_year, status, created_at) VALUES (:id, :name, :academic_year, :qs_year, :status, :created_at)'),
            {'id': session_id, 'name': 'Session Test Groq - Final', 'academic_year': '2025-2026', 'qs_year': 2025, 'status': 'active', 'created_at': datetime.utcnow()}
        )
        print(f'✅ Session créée: Session Test Groq - Final')
        print(f'   ID: {session_id}')

asyncio.run(create_session())