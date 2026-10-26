"""Password hashing and JWT tokens.

Passwords use PBKDF2 from Python's standard library, so there is no extra
dependency to explain. Each password gets its own random salt.
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    salt_b64, digest_b64 = stored.split("$")
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    # compare_digest takes the same time whether the first byte or the last byte differs.
    return hmac.compare_digest(actual, expected)


def create_token(user_id: int, team_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "team_id": team_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError if the token is forged, broken or expired."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
