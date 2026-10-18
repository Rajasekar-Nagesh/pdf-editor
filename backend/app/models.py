"""ORM models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    # We store only a SHA-256 hash of the token, never the token itself.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class StoredFile(Base):
    """A file in object storage. Owned either by a user or by an anonymous guest token."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    guest_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))  # pdf, docx, xlsx, pptx, image, zip, ...
    mime: Mapped[str] = mapped_column(String(127))
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # previous version (undo chain)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False)  # pinned to "My documents"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Job(Base):
    """A background processing job (one tool run)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    guest_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    tool: Mapped[str] = mapped_column(String(64))
    input_ids: Mapped[list] = mapped_column(JSON, default=list)
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # secrets are never stored here
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued, running, done, failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(255), default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Workflow(Base):
    """A saved batch action: an ordered list of tool steps."""

    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    steps: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewLink(Base):
    """A public link that lets anyone view a document and add comments."""

    __tablename__ = "review_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    comments: Mapped[list["ReviewComment"]] = relationship(back_populates="link", cascade="all, delete-orphan")


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    link_id: Mapped[str] = mapped_column(ForeignKey("review_links.id", ondelete="CASCADE"), index=True)
    author: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int] = mapped_column(Integer, default=0)
    x: Mapped[float | None] = mapped_column(nullable=True)
    y: Mapped[float | None] = mapped_column(nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    link: Mapped[ReviewLink] = relationship(back_populates="comments")


class SignatureRequest(Base):
    __tablename__ = "signature_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, default="")
    original_file_id: Mapped[str] = mapped_column(String(32))
    current_file_id: Mapped[str] = mapped_column(String(32))  # latest signed version
    audit_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending, completed, declined, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    signers: Mapped[list["Signer"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="Signer.order"
    )
    events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="AuditEvent.id"
    )


class Signer(Base):
    __tablename__ = "signers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(ForeignKey("signature_requests.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    order: Mapped[int] = mapped_column(Integer, default=1)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting")  # waiting, sent, viewed, signed, declined
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    request: Mapped[SignatureRequest] = relationship(back_populates="signers")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("signature_requests.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[SignatureRequest] = relationship(back_populates="events")
