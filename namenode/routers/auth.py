import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from auth import create_token, hash_password, verify_password
from metadata import get_conn, get_user

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str


def _require_admin(x_admin_token: str = Header(default="")):
    with get_conn() as conn:
        has_users = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    if has_users:
        if not ADMIN_SECRET or x_admin_token != ADMIN_SECRET:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Se requiere token de administrador")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, _: None = Depends(_require_admin)):
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (body.username, hash_password(body.password), now),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El usuario ya existe")
    return {"username": body.username, "created_at": now}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    user = get_user(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    return {"access_token": create_token(body.username), "token_type": "bearer"}
