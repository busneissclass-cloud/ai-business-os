"""Permission firewall API: read-only matrix + the server-side authz check."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AgentPermission, ToolPermission
from ..permissions import authorize, seed_permissions

router = APIRouter()


class CheckRequest(BaseModel):
    agent: str
    tool: str
    approval_id: str | None = None


@router.post("/permissions/seed")
def seed(db: Session = Depends(get_db)):
    seed_permissions(db)
    return {"seeded": True}


@router.get("/permissions/matrix")
def matrix(db: Session = Depends(get_db)):
    return {
        "agents": [{"agent": a.agent, "tools": a.allowed_tools,
                    "max_autonomy": a.max_autonomy} for a in db.query(AgentPermission).all()],
        "tools": [{"tool": t.tool, "risk": t.risk_level,
                   "requires_approval": t.requires_approval,
                   "forbidden": t.forbidden} for t in db.query(ToolPermission).all()],
    }


@router.post("/permissions/check")
def check(req: CheckRequest, db: Session = Depends(get_db)):
    result = authorize(db, req.agent, req.tool, req.approval_id)
    return {"agent": req.agent, "tool": req.tool,
            "allowed": result.allowed, "reason": result.reason}
