"""Shareable review links: anyone with the link can view the PDF and comment without an account.

Comments sync between viewers by polling `GET .../comments?since=<last id>` every few seconds.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..filestore import get_owned_file
from ..models import ReviewComment, ReviewLink, StoredFile, User
from ..schemas import CommentIn, ReviewLinkIn
from ..security import Identity, get_current_user, new_token
from ..storage import get_storage

router = APIRouter(tags=["review"])


def _link(link: ReviewLink, db: Session) -> dict:
    count = db.query(ReviewComment).filter(ReviewComment.link_id == link.id).count()
    return {
        "id": link.id,
        "token": link.token,
        "url": f"{get_settings().public_url}/review/{link.token}",
        "file_id": link.file_id,
        "title": link.title,
        "active": link.active,
        "comments": count,
        "created_at": link.created_at.isoformat(),
    }


def _comment(c: ReviewComment) -> dict:
    return {
        "id": c.id,
        "author": c.author,
        "text": c.text,
        "page": c.page,
        "x": c.x,
        "y": c.y,
        "parent_id": c.parent_id,
        "resolved": c.resolved,
        "created_at": c.created_at.isoformat(),
    }


@router.post("/api/review-links", status_code=201)
def create_link(body: ReviewLinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_owned_file(db, body.file_id, Identity(user=user, guest_token=None))
    if row.kind != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDFs can be shared for review.")
    row.is_saved = True  # keep shared documents
    link = ReviewLink(token=new_token(), file_id=row.id, owner_id=user.id, title=body.title or row.name)
    db.add(link)
    db.commit()
    return _link(link, db)


@router.get("/api/review-links")
def list_links(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ReviewLink).where(ReviewLink.owner_id == user.id).order_by(ReviewLink.created_at.desc())).all()
    return {"links": [_link(r, db) for r in rows]}


@router.delete("/api/review-links/{link_id}", status_code=204)
def disable_link(link_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    link = db.get(ReviewLink, link_id)
    if not link or link.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review link not found.")
    link.active = False
    db.commit()
    return Response(status_code=204)


def _active(db: Session, token: str) -> ReviewLink:
    link = db.scalar(select(ReviewLink).where(ReviewLink.token == token))
    if not link or not link.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This review link is invalid or has been disabled.")
    return link


@router.get("/api/public/review/{token}")
def review_info(token: str, db: Session = Depends(get_db)):
    link = _active(db, token)
    return {"title": link.title, "file_name": db.get(StoredFile, link.file_id).name}


@router.get("/api/public/review/{token}/document")
def review_document(token: str, db: Session = Depends(get_db)):
    link = _active(db, token)
    row = db.get(StoredFile, link.file_id)
    return Response(get_storage().get_bytes(row.storage_key), media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.get("/api/public/review/{token}/comments")
def list_comments(token: str, since: int = Query(0, ge=0), db: Session = Depends(get_db)):
    link = _active(db, token)
    rows = db.scalars(
        select(ReviewComment).where(ReviewComment.link_id == link.id, ReviewComment.id > since).order_by(ReviewComment.id)
    ).all()
    # Resolved flags can change on old comments, so also return the full list of resolved ids.
    resolved = db.scalars(select(ReviewComment.id).where(ReviewComment.link_id == link.id, ReviewComment.resolved.is_(True))).all()
    return {"comments": [_comment(c) for c in rows], "resolved_ids": list(resolved)}


@router.post("/api/public/review/{token}/comments", status_code=201)
def add_comment(token: str, body: CommentIn, db: Session = Depends(get_db)):
    link = _active(db, token)
    if body.parent_id is not None:
        parent = db.get(ReviewComment, body.parent_id)
        if not parent or parent.link_id != link.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The comment you replied to does not exist.")
    c = ReviewComment(
        link_id=link.id, author=body.author.strip(), text=body.text.strip(), page=body.page, x=body.x, y=body.y, parent_id=body.parent_id
    )
    db.add(c)
    db.commit()
    return _comment(c)


@router.post("/api/public/review/{token}/comments/{comment_id}/resolve")
def resolve_comment(token: str, comment_id: int, db: Session = Depends(get_db)):
    link = _active(db, token)
    c = db.get(ReviewComment, comment_id)
    if not c or c.link_id != link.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found.")
    c.resolved = not c.resolved
    db.commit()
    return _comment(c)
