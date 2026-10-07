from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import killswitch
from ..db import get_db, utcnow

router = APIRouter()


def _check_db(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        return f"error: {e}"


def _check_redis() -> str:
    try:
        import redis
        from ..config import settings
        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
        return "ok"
    except Exception:
        return "unavailable (fallback mode)"


@router.get("/health")
def health(db: Session = Depends(get_db)):
    ks = killswitch.is_killed()
    db_status = _check_db(db)
    redis_status = _check_redis()
    status = "ok" if db_status == "ok" else "degraded"
    return {
        "status": status,
        "db": db_status,
        "redis": redis_status,
        "kill_switch": ks,
        "time_utc": utcnow().isoformat(),
        "version": "0.1.0-m0",
    }
