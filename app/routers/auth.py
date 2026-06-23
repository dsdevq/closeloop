from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models import RefreshToken, User

router = APIRouter(prefix="/auth")

_bearer = HTTPBearer(auto_error=False)

_VALID_ROLES = {"admin", "manager", "rep"}


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    role: str = "rep"


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "created_at": user.created_at,
        "is_active": bool(user.is_active),
    }


@router.post("/register", status_code=201)
def register(
    body: RegisterRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(_VALID_ROLES)}")

    user_count = db.query(User).count()
    if user_count > 0:
        # Require admin auth for all subsequent registrations
        if credentials is None:
            raise HTTPException(status_code=401, detail="Admin authentication required to register new users")
        try:
            payload = decode_token(credentials.credentials)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        admin_id = int(payload["sub"])
        admin = db.query(User).filter(User.id == admin_id, User.is_active == 1).first()
        if not admin or admin.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required to register new users")

    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=422, detail="Email already registered")

    now = datetime.now(timezone.utc).isoformat()
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
        full_name=body.full_name,
        created_at=now,
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == 1).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user.id)
    refresh_token_str = create_refresh_token(user.id)

    now = datetime.now(timezone.utc).isoformat()
    token_row = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        created_at=now,
    )
    db.add(token_row)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_str,
        "token_type": "bearer",
        "user": _user_out(user),
    }


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    token_row = db.query(RefreshToken).filter(
        RefreshToken.token == body.refresh_token,
        RefreshToken.revoked_at.is_(None),
    ).first()
    if not token_row:
        raise HTTPException(status_code=401, detail="Refresh token revoked or not found")

    user = db.query(User).filter(User.id == token_row.user_id, User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Rotate: revoke old, issue new
    now = datetime.now(timezone.utc).isoformat()
    token_row.revoked_at = now

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    new_row = RefreshToken(user_id=user.id, token=new_refresh, created_at=now)
    db.add(new_row)
    db.commit()

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, db: Session = Depends(get_db)):
    token_row = db.query(RefreshToken).filter(
        RefreshToken.token == body.refresh_token,
        RefreshToken.revoked_at.is_(None),
    ).first()
    if token_row:
        token_row.revoked_at = datetime.now(timezone.utc).isoformat()
        db.commit()
    # Always 204 — don't reveal whether the token existed


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)


@router.get("/users")
def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).all()
    return [_user_out(u) for u in users]
