"""Run tools as jobs, poll job status, and manage saved batch actions (workflows)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import create_job, get_job_for, job_dict
from ..models import Job, User, Workflow
from ..schemas import ToolRun, WorkflowIn, WorkflowRun
from ..security import Identity, get_current_user, get_identity
from ..tools_registry import TOOLS, catalog

router = APIRouter(prefix="/api", tags=["tools"])


@router.get("/tools")
def list_tools():
    return {"tools": catalog()}


@router.post("/tools/{tool}", status_code=202)
def run_tool(tool: str, body: ToolRun, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    job = create_job(db, identity, tool, body.file_ids, body.params)
    return job_dict(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    job = get_job_for(db, job_id, identity)
    db.refresh(job)
    return job_dict(job)


@router.get("/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    q = select(Job)
    q = q.where(Job.owner_id == identity.user.id) if identity.user else q.where(Job.owner_id.is_(None), Job.guest_token == identity.guest_token)
    return {"jobs": [job_dict(j) for j in db.scalars(q.order_by(Job.created_at.desc()).limit(limit)).all()]}


# ------------------------------------------------------------------ workflows (saved batch actions)


def _validate_steps(steps) -> list[dict]:
    out = []
    for st in steps:
        spec = TOOLS.get(st.tool)
        if not spec or not spec.batchable:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{st.tool}' cannot be used in a batch action.")
        if any("password" in k.lower() for k in st.params):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passwords cannot be saved in batch actions.")
        out.append({"tool": st.tool, "params": st.params})
    return out


def _wf(w: Workflow) -> dict:
    return {"id": w.id, "name": w.name, "steps": w.steps, "created_at": w.created_at.isoformat()}


@router.get("/workflows")
def list_workflows(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Workflow).where(Workflow.owner_id == user.id).order_by(Workflow.created_at.desc())).all()
    return {"workflows": [_wf(w) for w in rows]}


@router.post("/workflows", status_code=201)
def create_workflow(body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    w = Workflow(owner_id=user.id, name=body.name.strip(), steps=_validate_steps(body.steps))
    db.add(w)
    db.commit()
    return _wf(w)


def _own_wf(db: Session, wf_id: str, user: User) -> Workflow:
    w = db.get(Workflow, wf_id)
    if not w or w.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch action not found.")
    return w


@router.put("/workflows/{wf_id}")
def update_workflow(wf_id: str, body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    w = _own_wf(db, wf_id, user)
    w.name = body.name.strip()
    w.steps = _validate_steps(body.steps)
    db.commit()
    return _wf(w)


@router.delete("/workflows/{wf_id}", status_code=204)
def delete_workflow(wf_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own_wf(db, wf_id, user))
    db.commit()
    return Response(status_code=204)


@router.post("/workflows/{wf_id}/run", status_code=202)
def run_workflow(
    wf_id: str,
    body: WorkflowRun,
    user: User = Depends(get_current_user),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    w = _own_wf(db, wf_id, user)
    job = create_job(db, identity, "batch", body.file_ids, {"steps": w.steps})
    return job_dict(job)
