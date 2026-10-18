"""Upload, list, download, rename, delete files, upload new versions and inspect PDFs."""
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..filestore import delete_file, download_to, file_dict, get_owned_file, safe_name, save_upload
from ..models import StoredFile
from ..schemas import FilePatch
from ..security import Identity, get_identity
from ..services.common import ToolError
from ..services.inspect import inspect
from ..storage import get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("", status_code=201)
def upload(files: list[UploadFile] = File(...), identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    if len(files) > 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload at most 50 files at a time.")
    return {"files": [file_dict(save_upload(db, f, identity)) for f in files]}


@router.get("")
def list_files(
    scope: str = Query("recent", pattern="^(recent|saved|all)$"),
    limit: int = Query(50, ge=1, le=500),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    q = select(StoredFile)
    if identity.user:
        q = q.where(StoredFile.owner_id == identity.user.id)
    else:
        q = q.where(StoredFile.owner_id.is_(None), StoredFile.guest_token == identity.guest_token)
    if scope == "saved":
        q = q.where(StoredFile.is_saved.is_(True))
    q = q.order_by(StoredFile.last_opened_at.desc() if scope == "recent" else StoredFile.created_at.desc()).limit(limit)
    return {"files": [file_dict(r) for r in db.scalars(q).all()]}


@router.get("/{file_id}")
def get_file(file_id: str, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    row = get_owned_file(db, file_id, identity)
    row.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    return file_dict(row)


@router.get("/{file_id}/download")
def download(file_id: str, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    row = get_owned_file(db, file_id, identity)
    data = get_storage().get_bytes(row.storage_key)
    return Response(
        content=data,
        media_type=row.mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.name)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{file_id}")
def update_file(file_id: str, body: FilePatch, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    row = get_owned_file(db, file_id, identity)
    if body.name is not None:
        ext = Path(row.name).suffix
        new = safe_name(body.name)
        row.name = new if new.lower().endswith(ext.lower()) else f"{new}{ext}"
    if body.is_saved is not None:
        if not identity.user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in to save documents to your account.")
        row.is_saved = body.is_saved
    db.commit()
    return file_dict(row)


@router.delete("/{file_id}", status_code=204)
def remove_file(file_id: str, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    delete_file(db, get_owned_file(db, file_id, identity))
    return Response(status_code=204)


@router.post("/{file_id}/versions", status_code=201)
def upload_version(
    file_id: str, file: UploadFile = File(...), identity: Identity = Depends(get_identity), db: Session = Depends(get_db)
):
    """Store a PDF edited in the browser (pdf-lib) as a new version of an existing file."""
    parent = get_owned_file(db, file_id, identity)
    file.filename = parent.name
    row = save_upload(db, file, identity, parent_id=parent.id)
    if row.kind != "pdf":
        delete_file(db, row)
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "A new version must be a PDF.")
    return file_dict(row)


@router.get("/{file_id}/inspect/{what}")
def inspect_file(
    file_id: str,
    what: str,
    page: int = Query(0, ge=0),
    q: str = Query("", max_length=200),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    row = get_owned_file(db, file_id, identity)
    if row.kind != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files can be inspected.")
    with tempfile.TemporaryDirectory() as tmp:
        path = download_to(row, Path(tmp))
        try:
            return {"result": inspect(path, what, page, q)}
        except ToolError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
