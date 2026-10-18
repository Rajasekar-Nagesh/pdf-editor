"""AI assistant endpoints. Disabled (status.enabled = false) when ANTHROPIC_API_KEY is not set."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..filestore import download_to, get_owned_file
from ..schemas import AiChatIn, AiFileIn
from ..security import Identity, get_identity
from ..services import ai
from ..services.common import ToolError

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def ai_status():
    return {"enabled": get_settings().ai_enabled}


def _run(fn, db: Session, identity: Identity, file_id: str, *args):
    if not get_settings().ai_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The AI assistant is not enabled on this server.")
    row = get_owned_file(db, file_id, identity)
    if row.kind != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The assistant works with PDF files.")
    with tempfile.TemporaryDirectory() as tmp:
        path = download_to(row, Path(tmp))
        try:
            return fn(path, *args)
        except ToolError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/summary")
def summary(body: AiFileIn, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    return _run(ai.summarize, db, identity, body.file_id)


@router.post("/chat")
def chat(body: AiChatIn, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    return _run(ai.chat, db, identity, body.file_id, body.messages)
