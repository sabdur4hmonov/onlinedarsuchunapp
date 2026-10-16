import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_password_hasher = PasswordHasher()

# A real argon2 hash used when the user does not exist, so that "unknown phone"
# and "wrong password" take roughly the same time (prevents user enumeration).
_DUMMY_HASH = _password_hasher.hash("dummy-password-for-timing")

ACCESS_TOKEN_TYPE = "access"
DEVICE_BINDING_TOKEN_TYPE = "device_binding"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """`password_hash` is None for an unknown user (or, later, an OTP-only user)."""
    try:
        if password_hash is None:
            _password_hasher.verify(_DUMMY_HASH, password)
            return False
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # Refresh tokens are long random strings, so a fast SHA-256 is enough here
    # (argon2 is needed only for low-entropy secrets such as passwords).
    return hashlib.sha256(token.encode()).hexdigest()


def _encode(payload: dict, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {**payload, "iat": now, "exp": now + expires_delta, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: uuid.UUID, session_id: uuid.UUID, device_id: str, role: str) -> str:
    settings = get_settings()
    return _encode(
        {"type": ACCESS_TOKEN_TYPE, "sub": str(user_id), "sid": str(session_id), "did": device_id, "role": role},
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_device_binding_token(*, user_id: uuid.UUID, device_id: str) -> str:
    """Short-lived proof that the password was already checked for this user + device."""
    settings = get_settings()
    return _encode(
        {"type": DEVICE_BINDING_TOKEN_TYPE, "sub": str(user_id), "did": device_id},
        timedelta(minutes=settings.device_binding_token_expire_minutes),
    )


def decode_token(token: str, expected_type: str) -> dict | None:
    """Returns the payload, or None if the token is invalid, expired or of another type."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
