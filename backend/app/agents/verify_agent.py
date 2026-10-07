"""Agent 2 — Verify. Evidence-based verification, nothing assumed.
Runs the M0.5 contact-verification + freshness engines over a lead and sets
status: VERIFIED | NEEDS_REVIEW | INVALID. A lead is never 'verified' on vibes."""
from __future__ import annotations

from .base import BaseAgent
from .. import verify as verify_engine
from ..freshness import compute_freshness, mark_field_verified
from ..models import ContactVerification, Lead
from ..db import utcnow


class VerifyAgent(BaseAgent):
    name = "verify"
    prompt_version = "verify-v1"

    def execute(self, task: str, params: dict) -> dict:
        if task == "verify_lead":
            return self._verify_lead(params.get("lead_id", ""))
        if task == "verify_batch":
            return self._verify_batch(params.get("limit", 20))
        return {"status": "unknown task", "task": task}

    def _verify_batch(self, limit: int) -> dict:
        leads = self.db.query(Lead).filter(
            Lead.status.in_(["NEW_LEAD", "RESEARCHED"])).limit(limit).all()
        results = [self._verify_lead(l.id) for l in leads]
        ok = sum(1 for r in results if r.get("status") == "VERIFIED")
        return {"processed": len(results), "verified": ok}

    def _verify_lead(self, lead_id: str) -> dict:
        self.check_tool("crm.read")
        self.check_tool("crm.write")
        lead = self.db.get(Lead, lead_id)
        if not lead:
            return {"status": "unknown_lead"}

        # Verify what we actually have; record exactly what was checked.
        checks: dict = {}
        email = lead.email or self._extract_email(lead.notes or "")
        if email:
            r = verify_engine.verify_email(email)
            checks["email"] = r["status"]
            self.db.add(ContactVerification(
                lead_id=lead_id, kind="email", value=r["value"],
                status=r["status"], confidence=r["confidence"],
                checks=r["checks"], verified_at=utcnow()))
            mark_field_verified(self.db, lead_id, "email", "verify-agent")
        if lead.phone:
            r = verify_engine.verify_phone(lead.phone)
            checks["phone"] = r["status"]
            self.db.add(ContactVerification(
                lead_id=lead_id, kind="phone", value=r["value"],
                status=r["status"], confidence=r["confidence"],
                checks=r["checks"], verified_at=utcnow()))
            mark_field_verified(self.db, lead_id, "phone", "verify-agent")

        fresh = compute_freshness(self.db, lead_id)

        statuses = set(checks.values())
        if statuses & {"VALID", "LIKELY_VALID"}:
            lead.status = "VERIFIED"
            outcome = "VERIFIED"
        elif "RISKY" in statuses:
            lead.status = "NEEDS_REVIEW"
            outcome = "NEEDS_REVIEW"
        elif statuses and statuses == {"INVALID"}:
            lead.status = "INVALID"
            outcome = "INVALID"
        else:
            # no contact to check — researched but not verifiable yet
            lead.status = "RESEARCHED" if lead.status == "NEW_LEAD" else lead.status
            outcome = lead.status
        self.db.commit()
        self.audit("verify_lead",
                   decision=f"{lead.business_name}: {outcome} checks={checks}",
                   output={"lead_id": lead_id, "outcome": outcome,
                           "freshness": fresh["freshness_status"]})
        return {"lead_id": lead_id, "status": outcome, "checks": checks,
                "freshness": fresh["freshness_status"]}

    @staticmethod
    def _extract_email(text: str) -> str | None:
        import re
        m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text or "")
        return m.group(0) if m else None
