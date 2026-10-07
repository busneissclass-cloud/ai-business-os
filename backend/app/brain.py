"""AI Business Brain (M0.5): daily brief assembled from LIVE data.
No fabricated metrics — every number is a real query. Unknowns stay UNKNOWN."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Approval, Lead, SecurityEvent


def daily_brief(db: Session) -> dict:
    by_status = dict(db.query(Lead.status, func.count(Lead.id))
                     .group_by(Lead.status).all())
    by_tier = dict(db.query(Lead.tier, func.count(Lead.id))
                   .group_by(Lead.tier).all())
    hottest = db.query(Lead).order_by(Lead.buying_intent_score.desc()).limit(3).all()
    pending_approvals = db.query(Approval).filter(
        Approval.status == "PENDING").count()
    sec_events = db.query(SecurityEvent).order_by(
        SecurityEvent.ts.desc()).limit(5).all()

    return {
        "date": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).date().isoformat(),
        "pipeline": {
            "total_leads": sum(by_status.values()),
            "by_status": by_status,
            "by_tier": {k or "UNSET": v for k, v in by_tier.items()},
        },
        "hottest_leads": [
            {"business_name": l.business_name, "status": l.status,
             "intent": l.buying_intent_level, "score": l.buying_intent_score}
            for l in hottest if (l.buying_intent_score or 0) > 0],
        "pending_approvals": pending_approvals,
        "security": [{"category": e.category, "severity": e.severity,
                      "source": e.source, "action": e.action_taken}
                     for e in sec_events],
        "note": "All figures from live DB. No estimates. Empty sections mean no data yet.",
    }
