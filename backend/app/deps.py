"""Shared dependencies: kill-switch gate for anything outbound-ish."""
from fastapi import HTTPException, Request

from . import killswitch


def require_system_alive(request: Request):
    state = killswitch.is_killed()
    if state["active"]:
        raise HTTPException(
            status_code=423,
            detail={"error": "kill_switch_active",
                    "reason": state["reason"],
                    "message": "Outbound activity halted by kill switch. Resume explicitly to continue."},
        )
    return True


def correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")
