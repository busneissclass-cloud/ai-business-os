"""Versioned settings. Every change audited; AI cannot silently mutate config."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..deps import correlation_id
from ..models import AuditLog, Setting

router = APIRouter()


class SettingPut(BaseModel):
    value: dict
    changed_by: str = "owner"


@router.get("/settings/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    row = db.get(Setting, key)
    if not row:
        raise HTTPException(404, "unknown setting")
    return {"key": row.key, "value": row.value, "version": row.version}


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingPut, request: Request, db: Session = Depends(get_db)):
    row = db.get(Setting, key)
    if not row:
        row = Setting(key=key, value=body.value, version=1)
        db.add(row)
    else:
        row.value = body.value
        row.version += 1
    db.add(AuditLog(agent="settings", action=f"SET {key}",
                    decision=f"changed_by={body.changed_by} version={row.version}",
                    result="ok", correlation_id=correlation_id(request), ts=utcnow()))
    db.commit()
    return {"key": key, "value": row.value, "version": row.version}
