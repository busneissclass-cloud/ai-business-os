"""Agent 4 — Prioritize. The daily work queue, ranked by revenue logic:
priority = lead_score x intent_multiplier x freshness_multiplier.
No vanity ordering — money first, always explainable."""
from __future__ import annotations

from .base import BaseAgent
from ..models import Lead

INTENT_MULT = {"VERY_HIGH": 1.5, "HIGH": 1.25, "MEDIUM": 1.0, "LOW": 0.8, "VERY_LOW": 0.6}


class PrioritizeAgent(BaseAgent):
    name = "prioritize"
    prompt_version = "prioritize-v1"

    def execute(self, task: str, params: dict) -> dict:
        if task == "build_queue":
            return self._build_queue(params.get("limit", 20))
        return {"status": "unknown task", "task": task}

    def _build_queue(self, limit: int) -> dict:
        self.check_tool("crm.read")
        leads = self.db.query(Lead).filter(
            Lead.status.in_(["SCORED", "VERIFIED", "CONTACTED", "QUALIFIED"])).all()
        ranked = []
        for lead in leads:
            base = lead.lead_score or 0
            intent_mult = INTENT_MULT.get(lead.buying_intent_level or "VERY_LOW", 0.6)
            # stale high-intent leads get a nudge, not a penalty (revalidate first)
            priority = round(base * intent_mult)
            ranked.append({
                "lead_id": lead.id,
                "business_name": lead.business_name,
                "status": lead.status,
                "tier": lead.tier,
                "lead_score": base,
                "intent": lead.buying_intent_level,
                "priority": priority,
                "why": (f"score {base} x intent {lead.buying_intent_level} "
                        f"(x{intent_mult}) = {priority}"),
            })
        ranked.sort(key=lambda r: -r["priority"])
        queue = ranked[:limit]
        for r in queue:
            lead = self.db.get(Lead, r["lead_id"])
            if lead and lead.status == "SCORED":
                lead.status = "PRIORITIZED"
        self.db.commit()
        self.audit("build_queue", decision=f"queue of {len(queue)} from {len(ranked)} leads",
                   output={"top": queue[0] if queue else None})
        return {"queue": queue, "total": len(ranked)}
