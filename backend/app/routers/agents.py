"""Agent API: list agents, run a task, seed defaults."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agents.registry import AGENT_DESCRIPTIONS, run_agent, seed_all
from ..db import get_db
from ..deps import correlation_id

router = APIRouter()


class RunIn(BaseModel):
    task: str
    params: dict = {}


@router.get("/agents")
def list_agents():
    return [{"name": n, "description": d}
            for n, d in AGENT_DESCRIPTIONS.items()]


@router.post("/agents/seed")
def seed(db: Session = Depends(get_db)):
    seed_all(db)
    return {"seeded": True}


@router.post("/agents/{name}/run")
def run(name: str, body: RunIn, request: Request, db: Session = Depends(get_db)):
    return run_agent(db, name, body.task, body.params,
                     correlation_id=correlation_id(request))
