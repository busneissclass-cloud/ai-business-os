"""Buying Intent Engine. SEPARATE from lead score (fit vs timing).
Signals decay (expires_at); duplicate observations of one event don't stack."""
from sqlalchemy.orm import Session

from .db import as_utc, utcnow
from .models import BuyingIntentSignal, Lead

# signal_type -> (factor, weight). Weights configurable via settings.buying_intent_weights.
SIGNAL_FACTORS: dict[str, tuple[str, int]] = {
    "explicit_inquiry": ("explicit_request", 15),
    "proposal_request": ("explicit_request", 15),
    "reply_to_outreach": ("engagement", 10),
    "meeting_request": ("explicit_request", 15),
    "new_website": ("website_change", 10),
    "website_redesign_signal": ("website_change", 10),
    "hiring_marketing": ("hiring", 10),
    "hiring_sales": ("hiring", 10),
    "ads_running": ("ads", 10),
    "ads_weak_landing": ("ads", 10),
    "new_business": ("urgency", 15),
    "new_location": ("urgency", 15),
    "funding": ("urgency", 15),
    "expansion": ("urgency", 15),
    "review_spike_negative": ("urgency", 15),
    "competitor_expansion": ("competitor", 5),
    "trigger_event": ("trigger", 5),
    "buying_post": ("recent_signal", 20),
}

LEVELS = [(91, "VERY_HIGH"), (75, "HIGH"), (50, "MEDIUM"), (25, "LOW"), (0, "VERY_LOW")]


def _level(score: int) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "VERY_LOW"


def compute_buying_intent(db: Session, lead_id: str) -> dict:
    lead = db.get(Lead, lead_id)
    if not lead:
        return {"error": "unknown lead"}
    now = utcnow()
    signals = db.query(BuyingIntentSignal).filter(
        BuyingIntentSignal.lead_id == lead_id).all()

    seen_events: set[str] = set()  # duplicate suppression: one event = one count
    score = 0
    reasons: list[dict] = []
    for s in signals:
        if s.expires_at and as_utc(s.expires_at) < now:
            continue  # decayed
        factor, weight = SIGNAL_FACTORS.get(s.signal_type, ("recent_signal", 5))
        dedup_key = f"{s.signal_type}:{s.evidence_url or s.evidence_text or s.id}"
        if dedup_key in seen_events:
            continue  # same underlying event observed again — don't inflate
        seen_events.add(dedup_key)
        strength_mult = (s.signal_strength or 3) / 3.0
        contrib = round(weight * strength_mult)
        score += contrib
        reasons.append({
            "signal": s.signal_type, "factor": factor, "contribution": contrib,
            "evidence_url": s.evidence_url, "confidence": s.confidence,
            "detected_at": s.detected_at.isoformat() if s.detected_at else None,
        })

    score = min(100, score)
    level = _level(score)
    lead.buying_intent_score = score
    lead.buying_intent_level = level
    lead.buying_intent_updated_at = now
    db.commit()
    return {"lead_id": lead_id, "buying_intent_score": score,
            "buying_intent_level": level, "reasons": reasons,
            "note": "Separate from lead score (fit). Timing signal only."}
