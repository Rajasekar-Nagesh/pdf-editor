"""Digital certificate signing. Runs inside the request so certificates/passwords stay in memory only."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..filestore import download_to, file_dict, get_owned_file, register_file
from ..schemas import DscCompleteIn, DscPrepareIn
from ..security import Identity, get_identity
from ..services.common import ToolError
from ..services.signature import dsc_complete, dsc_prepare, sign_pkcs12

router = APIRouter(prefix="/api/sign", tags=["sign"])
MAX_PFX = 64 * 1024


def _rect(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        rect = [float(v) for v in json.loads(value)]
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature box.") from exc
    if len(rect) != 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature box.")
    return rect


@router.post("/digital")
def sign_digital(
    file_id: str = Form(...),
    certificate: UploadFile = File(...),
    password: str = Form(""),
    page: int = Form(0),
    rect: str | None = Form(None),
    reason: str = Form(""),
    location: str = Form(""),
    contact: str = Form(""),
    tsa_url: str = Form(""),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    row = get_owned_file(db, file_id, identity)
    if row.kind != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files can be signed.")
    pfx = certificate.file.read(MAX_PFX + 1)
    if len(pfx) > MAX_PFX or not pfx:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That does not look like a .pfx/.p12 certificate file.")
    if tsa_url and not tsa_url.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The timestamp server must be an http(s) URL.")
    with tempfile.TemporaryDirectory() as tmp:
        src = download_to(row, Path(tmp))
        out = Path(tmp) / "signed.pdf"
        try:
            info = sign_pkcs12(src, out, pfx, password, int(page), _rect(rect), reason, location, contact, tsa_url)
        except ToolError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        finally:
            del pfx, password  # drop secrets as soon as possible
        new = register_file(db, out, f"{Path(row.name).stem}-signed.pdf", identity.user_id, identity.guest_token, parent_id=row.id)
    return {"file": file_dict(new), "signature": info}


def _state_token(data: dict) -> str:
    s = get_settings()
    payload = {"dsc": data, "exp": datetime.now(timezone.utc) + timedelta(minutes=15)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


@router.post("/dsc/prepare")
def prepare_dsc(body: DscPrepareIn, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    """Step 1 of USB token signing. Returns the bytes the token must sign and a tamper-proof state token."""
    row = get_owned_file(db, body.file_id, identity)
    with tempfile.TemporaryDirectory() as tmp:
        src = download_to(row, Path(tmp))
        prepared = Path(tmp) / "prepared.pdf"
        try:
            res = dsc_prepare(src, prepared, body.certificate, body.page, body.rect, body.reason, body.location, body.contact)
        except ToolError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        prep_row = register_file(db, prepared, f"{Path(row.name).stem}-prepared.pdf", identity.user_id, identity.guest_token)
    state = {**res["state"], "prepared_id": prep_row.id, "source_id": row.id}
    return {"to_sign": res["to_sign"], "digest_algorithm": res["digest_algorithm"], "state_token": _state_token(state)}


@router.post("/dsc/complete")
def complete_dsc(body: DscCompleteIn, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    s = get_settings()
    try:
        state = jwt.decode(body.state_token, s.jwt_secret, algorithms=[s.jwt_algorithm])["dsc"]
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The signing session expired. Please start again.") from exc
    prepared = get_owned_file(db, state["prepared_id"], identity)
    source = get_owned_file(db, state["source_id"], identity)
    with tempfile.TemporaryDirectory() as tmp:
        src = download_to(prepared, Path(tmp))
        out = Path(tmp) / "signed.pdf"
        try:
            info = dsc_complete(src, out, state, body.signature)
        except ToolError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        new = register_file(db, out, f"{Path(source.name).stem}-signed.pdf", identity.user_id, identity.guest_token, parent_id=source.id)
    from ..filestore import delete_file

    delete_file(db, prepared)
    return {"file": file_dict(new), "signature": info}
