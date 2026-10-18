"""Helpers that tie StoredFile rows to object storage and enforce ownership."""
import mimetypes
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .config import get_settings
from .models import StoredFile
from .security import Identity
from .storage import get_storage
from .validation import InvalidFile, sniff

CHUNK = 1024 * 1024

KIND_BY_EXT = {
    "pdf": ("pdf", "application/pdf"),
    "zip": ("zip", "application/zip"),
    "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "png": ("image", "image/png"),
    "jpg": ("image", "image/jpeg"),
    "jpeg": ("image", "image/jpeg"),
    "html": ("html", "text/html"),
    "txt": ("txt", "text/plain"),
    "json": ("json", "application/json"),
}


def safe_name(name: str, default: str = "file") -> str:
    """Strip path components and control characters from a user-supplied file name."""
    name = Path(name or default).name
    cleaned = "".join(c for c in name if c.isprintable() and c not in '<>:"/\\|?*').strip(" .")
    return (cleaned or default)[:200]


def _expiry(identity_user_id: str | None) -> datetime | None:
    if identity_user_id:
        return None  # account files are kept until the user deletes them
    return datetime.now(timezone.utc) + timedelta(minutes=get_settings().guest_file_ttl_minutes)


def register_file(
    db: Session,
    path: Path,
    name: str,
    owner_id: str | None,
    guest_token: str | None,
    kind: str | None = None,
    mime: str | None = None,
    parent_id: str | None = None,
) -> StoredFile:
    """Upload a local file to storage and create its DB row."""
    ext = Path(name).suffix.lower().lstrip(".")
    if kind is None or mime is None:
        kind, mime = KIND_BY_EXT.get(ext, ("bin", mimetypes.guess_type(name)[0] or "application/octet-stream"))
    file_id = uuid.uuid4().hex
    key = f"files/{file_id}"
    get_storage().put_file(key, path, mime)
    row = StoredFile(
        id=file_id,
        owner_id=owner_id,
        guest_token=guest_token,
        name=safe_name(name),
        kind=kind,
        mime=mime,
        size=path.stat().st_size,
        storage_key=key,
        parent_id=parent_id,
        expires_at=_expiry(owner_id),
    )
    db.add(row)
    db.commit()
    return row


def save_upload(db: Session, upload: UploadFile, identity: Identity, parent_id: str | None = None) -> StoredFile:
    """Stream an upload to a temp file with a hard size cap, validate content, then store it."""
    limit = get_settings().max_upload_bytes
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "upload"
        total = 0
        with open(dest, "wb") as out:
            while chunk := upload.file.read(CHUNK):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"File is larger than the {get_settings().max_upload_mb} MB limit.",
                    )
                out.write(chunk)
        try:
            ftype = sniff(dest, upload.filename or "")
        except InvalidFile as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
        name = safe_name(upload.filename or f"document.{ftype.ext}")
        # Make sure the extension matches the real content.
        if Path(name).suffix.lower().lstrip(".") not in {ftype.ext, "jpeg" if ftype.ext == "jpg" else ftype.ext, "tif"}:
            name = f"{Path(name).stem}.{ftype.ext}"
        return register_file(
            db, dest, name, identity.user_id, identity.guest_token, ftype.kind, ftype.mime, parent_id
        )


def can_access(row: StoredFile, identity: Identity) -> bool:
    if identity.user and row.owner_id == identity.user.id:
        return True
    if identity.guest_token and row.owner_id is None and row.guest_token == identity.guest_token:
        return True
    return False


def get_owned_file(db: Session, file_id: str, identity: Identity) -> StoredFile:
    row = db.get(StoredFile, file_id)
    if not row or not can_access(row, identity):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found or it has expired.")
    return row


def download_to(row: StoredFile, directory: Path, name: str | None = None) -> Path:
    dest = directory / (name or f"{row.id}_{row.name}")
    get_storage().get_file(row.storage_key, dest)
    return dest


def delete_file(db: Session, row: StoredFile) -> None:
    try:
        get_storage().delete(row.storage_key)
    finally:
        db.delete(row)
        db.commit()


def copy_to_temp(row: StoredFile) -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory()
    return tmp, download_to(row, Path(tmp.name))


def file_dict(row: StoredFile) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "mime": row.mime,
        "size": row.size,
        "parent_id": row.parent_id,
        "is_saved": row.is_saved,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_opened_at": row.last_opened_at.isoformat() if row.last_opened_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def move_tree(src: Path, dest: Path) -> None:
    shutil.move(str(src), str(dest))
