"""Kill switch API. STOP EVERYTHING bypasses confirmation by design."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import killswitch
from ..deps import require_system_alive

router = APIRouter()


class KillRequest(BaseModel):
    reason: str = "manual stop"


@router.get("/kill-switch")
def status():
    return killswitch.is_killed()


@router.post("/kill-switch")
def activate(req: KillRequest):
    # No confirmation by design — "STOP EVERYTHING" must be instant.
    return killswitch.activate(req.reason)


@router.post("/kill-switch/resume")
def resume():
    # Explicit resume only. Never automatic.
    return killswitch.resume()


@router.get("/outbound/demo")
def outbound_demo(alive: bool = Depends(require_system_alive)):
    """M0 demo gate: proves the kill switch blocks outbound paths."""
    return {"ok": True, "note": "M0 demo gate — reachable only when kill switch is off"}
