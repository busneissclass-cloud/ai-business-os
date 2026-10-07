"""Next-best-action API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import NextBestAction
from ..nba import generate_nba

router = APIRouter()


@router.get("/nba")
def list_nba(db: Session = Depends(get_db)):
    actions = generate_nba(db)
    rows = db.query(NextBestAction).filter(NextBestAction.status == "open").all()
    by_text = {r.action: r for r in rows}
    out = []
    for a in actions:
        r = by_text.get(a["action"])
        a["id"] = r.id if r else None
        out.append(a)
    return out


@router.post("/nba/{action_id}/complete")
def complete(action_id: str, db: Session = Depends(get_db)):
    r = db.get(NextBestAction, action_id)
    if not r:
        raise HTTPException(404, "unknown action")
    r.status = "completed"
    r.completed_at = utcnow()
    db.commit()
    return {"id": action_id, "status": "completed"}
