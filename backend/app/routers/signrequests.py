"""Send for signature: invite signers (in order), track status, remind, and produce an audit trail."""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..emailer import send_email
from ..filestore import download_to, file_dict, get_owned_file, register_file
from ..models import AuditEvent, SignatureRequest, Signer, StoredFile, User
from ..ratelimit import client_ip
from ..schemas import DeclineIn, SignRequestIn, SignSubmit
from ..security import Identity, get_current_user, new_token, sha256
from ..services.audit import build_audit_pdf
from ..services.common import ToolContext, ToolError
from ..services.signature import place_signature
from ..storage import get_storage

router = APIRouter(tags=["signature-requests"])


def _event(db: Session, req: SignatureRequest, actor: str, action: str, detail: str = "", request: Request | None = None):
    db.add(
        AuditEvent(
            request_id=req.id,
            actor=actor,
            action=action,
            detail=detail,
            ip=client_ip(request) if request else "",
            user_agent=(request.headers.get("user-agent", "")[:255] if request else ""),
        )
    )


def _req_dict(req: SignatureRequest) -> dict:
    return {
        "id": req.id,
        "title": req.title,
        "message": req.message,
        "status": req.status,
        "created_at": req.created_at.isoformat(),
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "original_file_id": req.original_file_id,
        "current_file_id": req.current_file_id,
        "audit_file_id": req.audit_file_id,
        "signers": [
            {
                "id": s.id,
                "name": s.name,
                "email": s.email,
                "order": s.order,
                "status": s.status,
                "signed_at": s.signed_at.isoformat() if s.signed_at else None,
            }
            for s in req.signers
        ],
        "events": [
            {"actor": e.actor, "action": e.action, "detail": e.detail, "at": e.created_at.isoformat()} for e in req.events
        ],
    }


def _invite(db: Session, req: SignatureRequest, signer: Signer, token: str, owner_name: str, reminder: bool = False) -> None:
    link = f"{get_settings().public_url}/sign/{token}"
    subject = f"{'Reminder: ' if reminder else ''}Please sign \"{req.title}\""
    body = (
        f"Hello {signer.name},\n\n{owner_name} has asked you to sign \"{req.title}\".\n\n"
        + (f"Message: {req.message}\n\n" if req.message else "")
        + f"Open this link to review and sign:\n{link}\n\nThis link is personal - please do not forward it."
    )
    send_email(signer.email, subject, body)
    if signer.status == "waiting":
        signer.status = "sent"
    signer.last_reminded_at = datetime.now(timezone.utc)


def _rotate_token(signer: Signer) -> str:
    """Links are stored only as hashes, so reminders issue a fresh link."""
    token = new_token()
    signer.token_hash = sha256(token)
    return token


def _current_order(req: SignatureRequest) -> int | None:
    pending = [s.order for s in req.signers if s.status not in ("signed",)]
    return min(pending) if pending else None


def _advance(db: Session, req: SignatureRequest, owner: User) -> None:
    """Email every signer in the next signing-order group that has not been invited yet."""
    order = _current_order(req)
    if order is None:
        return
    for s in req.signers:
        if s.order == order and s.status == "waiting":
            _invite(db, req, s, _rotate_token(s), owner.name or owner.email)
            _event(db, req, "system", "sent", f"Invitation emailed to {s.email}")


@router.post("/api/signature-requests", status_code=201)
def create_request(body: SignRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    identity = Identity(user=user, guest_token=None)
    row = get_owned_file(db, body.file_id, identity)
    if row.kind != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files can be sent for signature.")
    emails = [s.email.lower() for s in body.signers]
    if len(set(emails)) != len(emails):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each signer must have a different email address.")
    row.is_saved = True
    req = SignatureRequest(
        owner_id=user.id, title=body.title, message=body.message, original_file_id=row.id, current_file_id=row.id
    )
    db.add(req)
    db.flush()
    for s in body.signers:
        db.add(Signer(request_id=req.id, name=s.name, email=s.email.lower(), order=s.order, token_hash=sha256(new_token())))
    _event(db, req, user.email, "created", f"{len(body.signers)} signer(s)")
    db.commit()
    db.refresh(req)
    _advance(db, req, user)
    db.commit()
    db.refresh(req)
    return _req_dict(req)


@router.get("/api/signature-requests")
def list_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(SignatureRequest).where(SignatureRequest.owner_id == user.id).order_by(SignatureRequest.created_at.desc())
    ).all()
    return {"requests": [_req_dict(r) for r in rows]}


def _own_request(db: Session, req_id: str, user: User) -> SignatureRequest:
    req = db.get(SignatureRequest, req_id)
    if not req or req.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signature request not found.")
    return req


@router.get("/api/signature-requests/{req_id}")
def get_request(req_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _req_dict(_own_request(db, req_id, user))


@router.post("/api/signature-requests/{req_id}/remind")
def remind(req_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = _own_request(db, req_id, user)
    if req.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This request is no longer pending.")
    order = _current_order(req)
    sent = 0
    for s in req.signers:
        if s.order == order and s.status in ("sent", "viewed"):
            _invite(db, req, s, _rotate_token(s), user.name or user.email, reminder=True)
            _event(db, req, user.email, "reminded", f"Reminder emailed to {s.email}")
            sent += 1
    db.commit()
    return {"sent": sent}


@router.post("/api/signature-requests/{req_id}/cancel")
def cancel(req_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = _own_request(db, req_id, user)
    if req.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This request is no longer pending.")
    req.status = "cancelled"
    _event(db, req, user.email, "cancelled")
    db.commit()
    return _req_dict(req)


def send_reminders_for(db: Session, older_than: timedelta) -> int:
    """Automatic reminders, used by the scheduler."""
    cutoff = datetime.now(timezone.utc) - older_than
    sent = 0
    for req in db.scalars(select(SignatureRequest).where(SignatureRequest.status == "pending")).all():
        owner = db.get(User, req.owner_id)
        order = _current_order(req)
        for s in req.signers:
            last = s.last_reminded_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if s.order == order and s.status in ("sent", "viewed") and (last is None or last < cutoff):
                _invite(db, req, s, _rotate_token(s), owner.name or owner.email, reminder=True)
                _event(db, req, "system", "reminded", f"Automatic reminder to {s.email}")
                sent += 1
    db.commit()
    return sent


# ------------------------------------------------------------------ public signer endpoints


def _signer_by_token(db: Session, token: str) -> Signer:
    signer = db.scalar(select(Signer).where(Signer.token_hash == sha256(token)))
    if not signer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This signing link is invalid or has been replaced by a newer email.")
    return signer


@router.get("/api/public/sign/{token}")
def view_signing(token: str, request: Request, db: Session = Depends(get_db)):
    signer = _signer_by_token(db, token)
    req = signer.request
    can_sign = req.status == "pending" and signer.status in ("sent", "viewed") and _current_order(req) == signer.order
    if signer.status == "sent":
        signer.status = "viewed"
        _event(db, req, signer.email, "viewed", "", request)
        db.commit()
    return {
        "title": req.title,
        "message": req.message,
        "signer": {"name": signer.name, "email": signer.email, "status": signer.status},
        "request_status": req.status,
        "can_sign": can_sign,
        "signers": [{"name": s.name, "order": s.order, "status": s.status} for s in req.signers],
    }


@router.get("/api/public/sign/{token}/document")
def signing_document(token: str, db: Session = Depends(get_db)):
    signer = _signer_by_token(db, token)
    row = db.get(StoredFile, signer.request.current_file_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return Response(get_storage().get_bytes(row.storage_key), media_type="application/pdf", headers={"Cache-Control": "no-store"})


def _finish(db: Session, req: SignatureRequest, owner: User) -> None:
    """All signers done: create the audit trail PDF and email the owner and signers."""
    req.status = "completed"
    req.completed_at = datetime.now(timezone.utc)
    _event(db, req, "system", "completed", "All signers have signed")
    db.commit()
    db.refresh(req)
    original = db.get(StoredFile, req.original_file_id)
    final = db.get(StoredFile, req.current_file_id)
    with tempfile.TemporaryDirectory() as tmp:
        orig_path = download_to(original, Path(tmp), "original.pdf")
        final_path = download_to(final, Path(tmp), "final.pdf")
        audit_path = build_audit_pdf(req, orig_path, final_path, Path(tmp) / "audit.pdf")
        audit = register_file(db, audit_path, f"{Path(final.name).stem}-audit-trail.pdf", owner.id, None)
        audit.is_saved = True
        req.audit_file_id = audit.id
        db.commit()
        attachments = [
            (final.name, final_path.read_bytes(), "application/pdf"),
            (audit.name, audit_path.read_bytes(), "application/pdf"),
        ]
    for email in {owner.email, *[s.email for s in req.signers]}:
        send_email(email, f"Completed: \"{req.title}\"", f"All parties have signed \"{req.title}\". The signed document and audit trail are attached.", attachments)


@router.post("/api/public/sign/{token}/sign")
def submit_signature(token: str, body: SignSubmit, request: Request, db: Session = Depends(get_db)):
    signer = _signer_by_token(db, token)
    req = signer.request
    if req.status != "pending" or signer.status not in ("sent", "viewed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This document can no longer be signed with this link.")
    if _current_order(req) != signer.order:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please wait - earlier signers have not signed yet.")
    owner = db.get(User, req.owner_id)
    current = db.get(StoredFile, req.current_file_id)
    with tempfile.TemporaryDirectory() as tmp:
        src = download_to(current, Path(tmp))
        ctx = ToolContext(workdir=Path(tmp), inputs=[src], input_names=[current.name])
        try:
            out = place_signature(ctx, body.placements, image_data=body.image_data)
        except ToolError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        path, _ = out.files[0]
        new = register_file(db, path, f"{Path(db.get(StoredFile, req.original_file_id).name).stem}-signed.pdf", owner.id, None, parent_id=current.id)
    new.is_saved = True
    req.current_file_id = new.id
    signer.status = "signed"
    signer.signed_at = datetime.now(timezone.utc)
    _event(db, req, signer.email, "signed", f"{signer.name} signed on {len(body.placements)} location(s)", request)
    db.commit()
    db.refresh(req)
    if all(s.status == "signed" for s in req.signers):
        _finish(db, req, owner)
    else:
        _advance(db, req, owner)
        db.commit()
    return {"ok": True, "request_status": req.status}


@router.post("/api/public/sign/{token}/decline")
def decline(token: str, body: DeclineIn, request: Request, db: Session = Depends(get_db)):
    signer = _signer_by_token(db, token)
    req = signer.request
    if req.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This request is no longer pending.")
    signer.status = "declined"
    req.status = "declined"
    _event(db, req, signer.email, "declined", body.reason[:500], request)
    db.commit()
    owner = db.get(User, req.owner_id)
    send_email(owner.email, f"Declined: \"{req.title}\"", f"{signer.name} ({signer.email}) declined to sign.\nReason: {body.reason or '-'}")
    return {"ok": True}


@router.get("/api/signature-requests/{req_id}/files")
def request_files(req_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = _own_request(db, req_id, user)
    out = {}
    for key, fid in (("original", req.original_file_id), ("current", req.current_file_id), ("audit", req.audit_file_id)):
        row = db.get(StoredFile, fid) if fid else None
        out[key] = file_dict(row) if row else None
    return out
