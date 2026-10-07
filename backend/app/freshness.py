"""Lead Freshness Engine. Field-level freshness — never mark a whole lead fresh
because one field was checked. Critical changes -> RESEARCH_REQUIRED + OUTREACH_HOLD."""
from datetime import timedelta

from sqlalchemy.orm import Session

from .db import parse_dt, utcnow
from .models import Lead, LeadFreshness

# revalidation cadence per tier (days) — configurable via settings.freshness_cadence
CADENCE = {"HOT": 7, "HIGH": 14, "MEDIUM": 30, "LOW": 60}
TRACKED_FIELDS = ["website", "email", "phone", "decision_maker", "company",
                  "address", "social", "seo", "competitor", "buying_signal"]


def _level(age_days: float | None) -> str:
    if age_days is None:
        return "UNKNOWN"
    if age_days < 7:
        return "FRESH"
    if age_days < 30:
        return "RECENT"
    if age_days < 60:
        return "AGING"
    if age_days < 120:
        return "STALE"
    return "EXPIRED"


def compute_freshness(db: Session, lead_id: str) -> dict:
    lead = db.get(Lead, lead_id)
    if not lead:
        return {"error": "unknown lead"}
    row = db.get(LeadFreshness, lead_id)
    if not row:
        row = LeadFreshness(lead_id=lead_id, fields={})
        db.add(row)
    now = utcnow()
    fields_out: dict = {}
    scores = []
    for f in TRACKED_FIELDS:
        info = (row.fields or {}).get(f, {})
        verified_at = parse_dt(info.get("verified_at"))
        age = (now - verified_at).days if verified_at else None
        level = _level(age)
        fields_out[f] = {"verified_at": verified_at, "source": info.get("source"),
                         "age_days": age, "freshness": level}
        scores.append(100 if level == "FRESH" else 75 if level == "RECENT"
                      else 50 if level == "AGING" else 25 if level == "STALE"
                      else 0)
    overall = round(sum(scores) / len(scores)) if scores else 0
    status = _level(sum(s for s in scores) / 25) if False else (
        "FRESH" if overall >= 85 else "RECENT" if overall >= 65
        else "AGING" if overall >= 40 else "STALE" if overall >= 15 else "EXPIRED"
        if any(v["freshness"] != "UNKNOWN" for v in fields_out.values()) else "UNKNOWN")
    cadence_days = CADENCE.get(lead.tier or "LOW", 60)
    row.freshness_score = overall
    row.freshness_status = status
    row.last_checked_at = now
    row.next_check_at = now + timedelta(days=cadence_days)
    db.commit()
    return {"lead_id": lead_id, "freshness_score": overall, "freshness_status": status,
            "fields": fields_out, "next_check_at": row.next_check_at.isoformat()}


def mark_field_verified(db: Session, lead_id: str, field: str, source: str) -> None:
    row = db.get(LeadFreshness, lead_id)
    if not row:
        row = LeadFreshness(lead_id=lead_id, fields={})
        db.add(row)
    fields = dict(row.fields or {})
    fields[field] = {"verified_at": utcnow().isoformat(), "source": source}
    row.fields = fields
    db.commit()
