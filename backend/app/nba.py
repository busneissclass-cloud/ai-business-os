"""Next-Best-Action Engine. Prioritizes by revenue impact, not vanity.
Each action: what, why, priority, confidence, expected value, deadline, required approval."""
from datetime import timedelta

from sqlalchemy.orm import Session

from .db import as_utc, utcnow
from .models import Approval, Lead, NextBestAction

PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _add(db: Session, actions: list, **kw):
    kw.setdefault("status", "open")
    db.add(NextBestAction(**kw))
    actions.append(kw)


def generate_nba(db: Session) -> list[dict]:
    """Recompute today's NBA list from live data. Idempotent-ish: clears open actions first."""
    db.query(NextBestAction).filter(NextBestAction.status == "open").delete()
    db.commit()
    actions: list[dict] = []
    now = utcnow()
    leads = db.query(Lead).all()

    for lead in leads:
        intent = lead.buying_intent_level or "VERY_LOW"
        last_contact = as_utc(lead.last_contacted_at)
        days_since_contact = (now - last_contact).days if last_contact else 999

        if intent in ("VERY_HIGH", "HIGH") and days_since_contact > 3:
            _add(db, actions, lead_id=lead.id,
                 action=f"Priority outreach to {lead.business_name}",
                 reason=f"Buying intent {intent} ({lead.buying_intent_score}) and no contact for {days_since_contact}d",
                 priority="CRITICAL" if intent == "VERY_HIGH" else "HIGH",
                 confidence=80, expected_value="high — timing window open",
                 deadline=now + timedelta(days=2), required_approval="L2")
        if (lead.tier == "HOT" or intent in ("VERY_HIGH", "HIGH")) and days_since_contact > 14:
            _add(db, actions, lead_id=lead.id,
                 action=f"Revalidate lead data: {lead.business_name}",
                 reason="High-value lead going stale — verify before spending outreach",
                 priority="MEDIUM", confidence=70, expected_value="data quality",
                 deadline=now + timedelta(days=7), required_approval="L3")
        if lead.status in ("CONTACTED", "QUALIFIED") and days_since_contact > 7:
            _add(db, actions, lead_id=lead.id,
                 action=f"Follow up with {lead.business_name}",
                 reason=f"Conversation idle {days_since_contact}d at stage {lead.status}",
                 priority="HIGH", confidence=65, expected_value="pipeline momentum",
                 deadline=now + timedelta(days=3), required_approval="L3")

    pending = db.query(Approval).filter(Approval.status == "PENDING").count()
    if pending:
        _add(db, actions, lead_id=None,
             action=f"Review {pending} pending approval(s)",
             reason="High-risk actions waiting on human decision",
             priority="HIGH", confidence=100, expected_value="unblock pipeline",
             deadline=now + timedelta(days=1), required_approval="L2")

    db.commit()
    actions.sort(key=lambda a: (PRIORITY_RANK[a["priority"]], -a.get("confidence", 0)))
    return [{"id": a.get("id"), **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                   for k, v in a.items() if k != "id"}} for a in actions]
