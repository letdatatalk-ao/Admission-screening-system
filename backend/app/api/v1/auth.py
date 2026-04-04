from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from uuid import UUID

# Configuration (à mettre dans .env normalement)
SECRET_KEY = "KU_SCREENING_SECRET_KEY_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 heures

# Correction pour la compatibilité bcrypt 4.0+ et Python 3.12
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__ident="2b" 
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

# --- Logique Hash & Token ---

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Dépendances de Rôles ---

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        user_id: str = payload.get("id")
        if email is None:
            raise credentials_exception
        return {"email": email, "role": role, "id": user_id}
    except JWTError:
        raise credentials_exception

def check_admin(user = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def check_evaluator(user = Depends(get_current_user)):
    if user["role"] not in ["admin", "evaluator"]:
        raise HTTPException(status_code=403, detail="Evaluator access required")
    return user

from fastapi import APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from backend.app.db.database import SessionLocal
from backend.app.db.models import User
from sqlalchemy import select

router = APIRouter(tags=["Auth"])

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == form_data.username))
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        
        # On génère le token
        access_token = create_access_token(
            data={"sub": user.email, "role": user.role, "id": str(user.id)}
        )
        return {"access_token": access_token, "token_type": "bearer"}