import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "closeloop-jwt-secret-changeme-in-production")
_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": str(uuid.uuid4()),  # unique per issuance
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),  # guarantees uniqueness even for rapid successive calls
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError."""
    return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
