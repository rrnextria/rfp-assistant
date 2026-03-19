from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import get_settings
from common.db import get_db
from common.logging import get_logger

logger = get_logger("api-gateway.auth")
router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
limiter = Limiter(key_func=get_remote_address)

VALID_ROLES = {"end_user", "content_admin", "system_admin"}


# --- Pydantic schemas ---

class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    role: str = "end_user"
    teams: list[str] = []
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    teams: list[str]


# --- Helpers ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# --- Auth dependency ---

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    row = await db.execute(text("SELECT id, email, name, role FROM users WHERE id = :id"), {"id": user_id})
    user = row.mappings().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    teams_result = await db.execute(
        text("SELECT t.name FROM teams t JOIN user_teams ut ON t.id = ut.team_id WHERE ut.user_id = :uid"),
        {"uid": user_id},
    )
    teams = [r[0] for r in teams_result.fetchall()]
    return {"id": str(user["id"]), "email": user["email"], "name": user["name"], "role": user["role"], "teams": teams}


# --- Endpoints ---

@users_router.post("", status_code=201)
async def create_user(req: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    if req.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of {VALID_ROLES}")

    existing = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": req.email})
    if existing.first():
        raise HTTPException(409, "User with that email already exists")

    user_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, name, role, password_hash) "
            "VALUES (:id, :email, :name, :role, :pw)"
        ),
        {"id": user_id, "email": req.email, "name": req.name, "role": req.role, "pw": hash_password(req.password)},
    )

    for team_name in req.teams:
        team_row = await db.execute(text("SELECT id FROM teams WHERE name = :name"), {"name": team_name})
        team = team_row.first()
        if team:
            team_id = str(team[0])
        else:
            team_id = str(uuid.uuid4())
            await db.execute(
                text("INSERT INTO teams (id, name) VALUES (:id, :name)"),
                {"id": team_id, "name": team_name},
            )
        await db.execute(
            text("INSERT INTO user_teams (user_id, team_id) VALUES (:uid, :tid) ON CONFLICT DO NOTHING"),
            {"uid": user_id, "tid": team_id},
        )

    await db.commit()
    return {"user_id": user_id}


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        text("SELECT id, role, password_hash FROM users WHERE email = :email"),
        {"email": req.email},
    )
    user = row.mappings().first()
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(str(user["id"]), user["role"])
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)
