"""Password hashing, JWT handling and request identity dependencies."""
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

GUEST_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; we reject longer passwords at the schema level.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=s.jwt_expire_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def new_token() -> str:
    """URL-safe random token for links (reset, review, signing)."""
    return secrets.token_urlsafe(32)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class Identity:
    """Who is making the request: a logged-in user, an anonymous guest, or both unknown."""

    user: User | None
    guest_token: str | None

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None


def _user_from_header(authorization: str | None, db: Session) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please log in again.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found.")
    return user


def get_identity(
    authorization: str | None = Header(default=None),
    x_guest_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Identity:
    """Resolve a user (JWT) or a guest (X-Guest-Token header). One of the two is required."""
    user = _user_from_header(authorization, db)
    guest = x_guest_token if x_guest_token and GUEST_TOKEN_RE.match(x_guest_token) else None
    if not user and not guest:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing credentials. Log in or send an X-Guest-Token header.")
    return Identity(user=user, guest_token=None if user else guest)


def get_current_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User:
    user = _user_from_header(authorization, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in to use this feature.")
    return user
