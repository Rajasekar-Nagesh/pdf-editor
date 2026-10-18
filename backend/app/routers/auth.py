"""Sign up, log in, current user, password reset by email."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..emailer import send_email
from ..models import PasswordResetToken, User
from ..schemas import ForgotIn, LoginIn, ResetIn, SignupIn
from ..security import create_access_token, get_current_user, hash_password, new_token, sha256, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/signup", status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": create_access_token(user.id), "user": _user_out(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return {"token": create_access_token(user.id), "user": _user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    """Always returns the same response so attackers cannot discover which emails exist."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user:
        token = new_token()
        s = get_settings()
        db.add(
            PasswordResetToken(
                token_hash=sha256(token),
                user_id=user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=s.password_reset_expire_minutes),
            )
        )
        db.commit()
        link = f"{s.public_url}/reset-password?token={token}"
        send_email(
            user.email,
            "Reset your PDFDesk password",
            f"Hello{(' ' + user.name) if user.name else ''},\n\nUse this link to choose a new password "
            f"(valid for {s.password_reset_expire_minutes} minutes):\n\n{link}\n\n"
            "If you did not ask for this, you can ignore this email.",
        )
    return {"ok": True, "message": "If that email has an account, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    row = db.get(PasswordResetToken, sha256(body.token))
    expires = row.expires_at if row else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not row or row.used or expires < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")
    user = db.get(User, row.user_id)
    user.password_hash = hash_password(body.password)
    row.used = True
    db.commit()
    return {"token": create_access_token(user.id), "user": _user_out(user)}
