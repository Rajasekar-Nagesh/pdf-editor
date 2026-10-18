"""Job creation and execution. Heavy work runs in the RQ worker so the API stays responsive."""
import logging
import shutil
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .filestore import download_to, file_dict, get_owned_file, register_file
from .models import Job, StoredFile
from .security import Identity
from .services.common import ToolContext, ToolError
from .tools_registry import TOOLS, call_tool

log = logging.getLogger("pdfdesk.jobs")
SECRET_KEYS = ("password", "secret", "pfx", "token")


def _scrub(params: dict) -> dict:
    """Remove anything that looks like a secret before persisting params."""
    return {k: ("***" if any(s in k.lower() for s in SECRET_KEYS) else v) for k, v in params.items()}


def _asset_ids(params: dict) -> dict[str, str]:
    return {k: v for k, v in params.items() if k.endswith("_file_id") and isinstance(v, str) and v}


def _collect_asset_ids(params: dict) -> dict[str, str]:
    """Asset ids may also appear inside batch steps."""
    ids = _asset_ids(params)
    for step in params.get("steps", []) or []:
        if isinstance(step, dict):
            ids.update(_asset_ids(step.get("params") or {}))
    return ids


def job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "tool": job.tool,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def create_job(db: Session, identity: Identity, tool: str, file_ids: list[str], params: dict) -> Job:
    spec = TOOLS.get(tool)
    if not spec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown tool '{tool}'.")
    if not (spec.min_files <= len(file_ids) <= spec.max_files):
        if spec.max_files == spec.min_files:
            msg = f"This tool needs exactly {spec.min_files} file(s)." if spec.min_files else "This tool does not take files."
        else:
            msg = f"This tool needs between {spec.min_files} and {spec.max_files} files."
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    for fid in file_ids:
        row = get_owned_file(db, fid, identity)
        if row.kind not in spec.accepts:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f'"{row.name}" is not a supported input for this tool ({", ".join(sorted(spec.accepts))}).'
            )
    for fid in _collect_asset_ids(params).values():
        get_owned_file(db, fid, identity)

    job = Job(
        owner_id=identity.user_id,
        guest_token=identity.guest_token,
        tool=tool,
        input_ids=list(file_ids),
        params=_scrub(params),
    )
    db.add(job)
    db.commit()

    s = get_settings()
    if spec.inline or s.job_mode == "sync":
        # Inline tools receive secrets directly from memory and never touch Redis or the DB.
        execute_job(job.id, params)
        db.refresh(job)
    else:
        from redis import Redis
        from rq import Queue

        queue = Queue("pdfdesk", connection=Redis.from_url(s.redis_url))
        queue.enqueue(execute_job, job.id, job_timeout=s.job_timeout_seconds, result_ttl=3600, failure_ttl=86400)
    return job


def _update(job_id: str, **fields) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job:
            for k, v in fields.items():
                setattr(job, k, v)
            db.commit()


def execute_job(job_id: str, params: dict | None = None) -> None:
    """Run a job: download inputs, call the tool, upload outputs, store the result."""
    db = SessionLocal()
    job = db.get(Job, job_id)
    if not job:
        db.close()
        return
    params = params if params is not None else dict(job.params or {})
    spec = TOOLS[job.tool]
    _update(job_id, status="running", progress=1, message="Starting")
    tmp = tempfile.mkdtemp(prefix="pdfdesk-")
    workdir = Path(tmp)
    try:
        identity = Identity(user=None, guest_token=job.guest_token)
        rows = [db.get(StoredFile, fid) for fid in job.input_ids]
        if any(r is None for r in rows):
            raise ToolError("An input file has expired. Please upload it again.")
        inputs = [download_to(r, workdir, f"in{n}_{r.name}") for n, r in enumerate(rows)]
        assets = {}
        for key, fid in _collect_asset_ids(params).items():
            row = db.get(StoredFile, fid)
            if row is None:
                raise ToolError("An attached file has expired. Please upload it again.")
            asset_dir = workdir / "assets" / key
            asset_dir.mkdir(parents=True)
            assets[key] = download_to(row, asset_dir, row.name)

        last = {"pct": 0}

        def progress(pct: int, msg: str = "") -> None:
            pct = max(1, min(99, int(pct)))
            if pct - last["pct"] >= 5 or msg:
                last["pct"] = pct
                _update(job_id, progress=pct, message=msg[:250])

        ctx = ToolContext(
            workdir=workdir, inputs=inputs, input_names=[r.name for r in rows], assets=assets, progress=progress
        )
        output = call_tool(job.tool, ctx, params)

        owner_id = job.owner_id
        guest = job.guest_token if not owner_id else None
        parent = job.input_ids[0] if spec.versioned and len(job.input_ids) == 1 and len(output.files) == 1 else None
        files = [register_file(db, path, name, owner_id, guest, parent_id=parent) for path, name in output.files]
        zip_row = None
        if len(output.files) > 1:
            zpath = workdir / "results.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                used = set()
                for path, name in output.files:
                    arc = name
                    k = 1
                    while arc in used:
                        k += 1
                        arc = f"{Path(name).stem}-{k}{Path(name).suffix}"
                    used.add(arc)
                    zf.write(path, arc)
            base = Path(identity_name(rows)).stem if rows else job.tool
            zip_row = register_file(db, zpath, f"{base}-{job.tool}.zip", owner_id, guest)
        result = {"files": [file_dict(f) for f in files], "zip": file_dict(zip_row) if zip_row else None, "data": output.data}
        _update(job_id, status="done", progress=100, message="Done", result=result, finished_at=datetime.now(timezone.utc))
    except ToolError as exc:
        _update(job_id, status="failed", error=str(exc), message="Failed", finished_at=datetime.now(timezone.utc))
    except Exception as exc:  # unexpected: log the stack (never file contents) and show a generic message
        log.error("Job %s (%s) crashed: %s\n%s", job_id, job.tool, exc.__class__.__name__, traceback.format_exc(limit=8))
        _update(
            job_id,
            status="failed",
            error="Something went wrong while processing this file. Please check the file and try again.",
            message="Failed",
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()
        shutil.rmtree(tmp, ignore_errors=True)


def identity_name(rows: list[StoredFile]) -> str:
    return rows[0].name if rows else "results"


def get_job_for(db: Session, job_id: str, identity: Identity) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    if identity.user and job.owner_id == identity.user.id:
        return job
    if identity.guest_token and job.owner_id is None and job.guest_token == identity.guest_token:
        return job
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
