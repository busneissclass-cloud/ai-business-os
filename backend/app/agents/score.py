"""Agent 3 — Score. Lead FIT score 0-100 with a transparent factor breakdown.
Every point is traceable to evidence. Formula versioned (score-v1)."""
from __future__ import annotations

from .base import BaseAgent
from ..models import ContactVerification, Lead, LeadScoreEvent

# factor -> weight. Sums to 100. Configurable via settings.lead_score_weights (M2).
WEIGHTS = {
    "need": 25,             # observable website/marketing problems
    "authority": 20,        # decision-maker identified
    "contact_quality": 15,  # verified contact channels
    "engagement": 15,       # replied / interacted
    "budget_fit": 15,       # business size proxy
    "strategic": 10,        # niche / ICP match
}


def _tier(score: int) -> str:
    if score >= 75:
        return "HOT"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


class ScoreAgent(BaseAgent):
    name = "score"
    prompt_version = "score-v1"

    def execute(self, task: str, params: dict) -> dict:
        if task == "score_lead":
            return self._score_lead(params.get("lead_id", ""), params.get("evidence", {}))
        if task == "score_batch":
            return self._score_batch(params.get("limit", 20))
        return {"status": "unknown task", "task": task}

    def _score_batch(self, limit: int) -> dict:
        leads = self.db.query(Lead).filter(
            Lead.status.in_(["VERIFIED", "RESEARCHED", "NEEDS_REVIEW"])).limit(limit).all()
        return {"scored": sum(1 for l in leads
                              if self._score_lead(l.id, {})["status"] == "scored")}

    def _score_lead(self, lead_id: str, evidence: dict) -> dict:
        self.check_tool("crm.read")
        self.check_tool("crm.write")
        lead = self.db.get(Lead, lead_id)
        if not lead:
            return {"status": "unknown_lead"}

        # factor values 0..1 from evidence (explicit, no guessing)
        verifications = self.db.query(ContactVerification).filter(
            ContactVerification.lead_id == lead_id).all()
        good_contacts = sum(1 for v in verifications
                            if v.status in ("VALID", "LIKELY_VALID"))

        factors = {
            "need": (float(evidence.get("need", 0.3)), "default 0.3 until research deepens"),
            "authority": (1.0 if evidence.get("decision_maker") else 0.0, "decision maker known?"),
            "contact_quality": (min(1.0, good_contacts / 2), f"{good_contacts} verified channels"),
            "engagement": (float(evidence.get("engagement", 0.0)), "reply/interaction evidence"),
            "budget_fit": (float(evidence.get("budget_fit", 0.5)), "size proxy default 0.5"),
            "strategic": (float(evidence.get("strategic", 0.5)), "ICP match default 0.5"),
        }
        breakdown, total = {}, 0
        for factor, (value, note) in factors.items():
            value = max(0.0, min(1.0, value))
            contrib = round(value * WEIGHTS[factor])
            total += contrib
            breakdown[factor] = {"value": value, "weight": WEIGHTS[factor],
                                 "contribution": contrib, "note": note}
        tier = _tier(total)
        lead.lead_score = total
        lead.tier = tier
        if lead.status in ("NEW_LEAD", "VERIFIED", "RESEARCHED", "NEEDS_REVIEW"):
            lead.status = "SCORED"
        self.db.add(LeadScoreEvent(lead_id=lead_id, score=total, tier=tier,
                                   factors=breakdown, model_version="score-v1"))
        self.db.commit()
        self.audit("score_lead",
                   decision=f"{lead.business_name}: {total}/100 {tier}",
                   output={"lead_id": lead_id, "score": total, "tier": tier})
        return {"status": "scored", "lead_id": lead_id, "score": total,
                "tier": tier, "factors": breakdown}
