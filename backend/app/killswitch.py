"""Global kill switch. Redis-first (<1s propagation), DB-backed fallback.
STOP EVERYTHING bypasses confirmation. Resume is explicit and audited."""
from datetime import datetime

import redis

from .config import settings
from .db import SessionLocal, utcnow
from .models import AuditLog, Setting

_redis = None
_memory_flag = {"active": False, "reason": None, "at": None}


def _get_redis():
    global _redis
    if _redis is None:
        try:
            _redis = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            _redis.ping()
        except Exception:
            _redis = False
    return _redis or None


def is_killed() -> dict:
    r = _get_redis()
    if r is not None:
        try:
            val = r.get(settings.KILL_SWITCH_KEY)
            if val:
                return {"active": True, "reason": val.decode(), "source": "redis"}
        except Exception:
            pass
    if _memory_flag["active"]:
        return {"active": True, "reason": _memory_flag["reason"], "source": "memory"}
    try:
        db = SessionLocal()
        row = db.get(Setting, "kill_switch")
        db.close()
        if row and row.value.get("active"):
            return {"active": True, "reason": row.value.get("reason"), "source": "db"}
    except Exception:
        pass
    return {"active": False, "reason": None, "source": None}


def activate(reason: str, actor: str = "owner") -> dict:
    state = {"active": True, "reason": reason, "at": utcnow().isoformat(), "by": actor}
    r = _get_redis()
    if r is not None:
        try:
            r.set(settings.KILL_SWITCH_KEY, reason)
        except Exception:
            pass
    _memory_flag.update({"active": True, "reason": reason, "at": state["at"]})
    try:
        db = SessionLocal()
        row = db.get(Setting, "kill_switch")
        if not row:
            row = Setting(key="kill_switch", value={})
            db.add(row)
        row.value = state
        row.version += 1
        db.add(AuditLog(agent="kill-switch", action="ACTIVATE",
                        decision=f"reason={reason}", result="ok",
                        correlation_id=None, ts=utcnow()))
        db.commit()
        db.close()
    except Exception:
        pass
    return state


def resume(actor: str = "owner") -> dict:
    r = _get_redis()
    if r is not None:
        try:
            r.delete(settings.KILL_SWITCH_KEY)
        except Exception:
            pass
    _memory_flag.update({"active": False, "reason": None, "at": None})
    try:
        db = SessionLocal()
        row = db.get(Setting, "kill_switch")
        if row:
            row.value = {"active": False, "resumed_by": actor, "at": utcnow().isoformat()}
            row.version += 1
        db.add(AuditLog(agent="kill-switch", action="RESUME",
                        decision=f"resumed_by={actor}", result="ok",
                        correlation_id=None, ts=utcnow()))
        db.commit()
        db.close()
    except Exception:
        pass
    return {"active": False, "resumed_by": actor}
