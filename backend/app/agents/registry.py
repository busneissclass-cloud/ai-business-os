"""Agent registry: the 7 M1 agents. run_agent() is the single entry point."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .base import BaseAgent
from .compliance import seed_compliance
from .conversation import ConversationAgent
from .outreach import OutreachAgent
from .prioritize import PrioritizeAgent
from .research import ResearchAgent
from .score import ScoreAgent
from .verify_agent import VerifyAgent
from ..permissions import seed_permissions

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "compliance": None,  # veto-only, no run loop; precheck via compliance_precheck
    "research": ResearchAgent,
    "verify": VerifyAgent,
    "score": ScoreAgent,
    "prioritize": PrioritizeAgent,
    "outreach": OutreachAgent,
    "conversation": ConversationAgent,
}

AGENT_DESCRIPTIONS = {
    "compliance": "Veto gate: quiet hours, opt-outs, channel rules, shadow mode",
    "research": "Discovery: ingest + dedupe candidates, trust-scan everything",
    "verify": "Evidence-based contact verification + freshness",
    "score": "Transparent 0-100 fit score + tier",
    "prioritize": "Revenue-ranked daily work queue",
    "outreach": "Drafts (A/B) + approval requests; never sends in shadow",
    "conversation": "Inbound classification, objection drafts, instant opt-out",
}


def run_agent(db: Session, name: str, task: str, params: dict | None = None,
              correlation_id: str | None = None) -> dict:
    cls = AGENT_CLASSES.get(name)
    if cls is None:
        return {"status": "unknown_agent" if name != "compliance" else "veto_only",
                "agent": name}
    agent = cls(db, correlation_id=correlation_id)
    return agent.run(task, params or {})


def seed_all(db: Session) -> None:
    seed_permissions(db)
    seed_compliance(db)
