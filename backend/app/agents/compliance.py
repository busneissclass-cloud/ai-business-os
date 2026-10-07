"""Agent 0 — Compliance. Veto power over every high-stakes action.
Deterministic rules, not judgment calls. Runs BEFORE the action, never after."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import AuditLog, Objection, OptOut, Setting
from ..security import redact_pii
from .base import shadow_mode_on

# action -> (risk, max allowed autonomy, needs_consent_channel_rules)
ACTION_POLICY = {
    "outreach.send": {"risk": "HIGH", "cap": "L2"},
    "call.place": {"risk": "CRITICAL", "cap": "L2"},
    "billing.invoice_issue": {"risk": "HIGH", "cap": "L2"},
    "contract.sign": {"risk": "CRITICAL", "cap": "L2"},
}

# Cold outreach channel rules (architecture: cold WhatsApp = NOT allowed)
COLD_CHANNEL_RULES = {
    "whatsapp": "blocked",   # cold WhatsApp prohibited; only existing conversations
    "email": "allowed",      # with opt-out honored + approval
    "linkedin": "manual",    # drafts only, human sends
    "call": "approval",      # warm leads only + approval
}


def _quiet_hours_active(db: Session) -> tuple[bool, str]:
    row = db.get(Setting, "quiet_hours")
    cfg = row.value if row else {"start": "21:00", "end": "09:00", "tz": "Asia/Karachi"}
    try:
        now = datetime.now(ZoneInfo(cfg.get("tz", "Asia/Karachi")))
        start = datetime.strptime(cfg.get("start", "21:00"), "%H:%M").time()
        end = datetime.strptime(cfg.get("end", "09:00"), "%H:%M").time()
        t = now.time()
        active = (t >= start or t <= end) if start > end else (start <= t <= end)
        return active, f"quiet hours {cfg.get('start')}-{cfg.get('end')} {cfg.get('tz')}"
    except Exception:
        return False, "quiet hours misconfigured"


def compliance_precheck(db: Session, agent: str, action: str, payload: dict) -> dict:
    """Returns {allowed, reasons[], shadow_downgrade}. Fail-closed."""
    reasons: list[str] = []
    blocked = False
    shadow_downgrade = False

    from .. import killswitch
    ks = killswitch.is_killed()
    if ks["active"]:
        return {"allowed": False, "reasons": ["kill switch active"], "shadow_downgrade": False}

    policy = ACTION_POLICY.get(action)
    if policy and shadow_mode_on(db):
        shadow_downgrade = True
        reasons.append("shadow mode: outbound downgraded to draft-only")

    # opt-out check
    target = str(payload.get("to") or payload.get("email") or payload.get("phone") or "")
    channel = str(payload.get("channel", ""))
    if target:
        hit = db.query(OptOut).filter(OptOut.value == target.lower()).first()
        if hit:
            blocked = True
            reasons.append(f"opt-out on record for {target} ({hit.reason or 'no reason'})")

    # quiet hours (outbound only)
    if action in ACTION_POLICY:
        quiet, desc = _quiet_hours_active(db)
        if quiet:
            blocked = True
            reasons.append(f"quiet hours active ({desc})")

    # cold channel rules
    if action == "outreach.send" and channel:
        rule = COLD_CHANNEL_RULES.get(channel, "blocked")
        if rule == "blocked":
            blocked = True
            reasons.append(f"cold outreach via {channel} prohibited by policy")
        elif rule == "manual":
            shadow_downgrade = True
            reasons.append(f"{channel} outreach is manual-send only; draft prepared")
        if not payload.get("consent", False) and channel == "whatsapp":
            blocked = True
            reasons.append("whatsapp requires existing conversation / consent")

    # PII hygiene note (non-blocking, redaction applied downstream)
    redacted = redact_pii(str(payload.get("body", "")))
    if redacted != str(payload.get("body", "")):
        reasons.append("PII detected in payload — will be redacted in logs")

    return {"allowed": not blocked, "reasons": reasons,
            "shadow_downgrade": shadow_downgrade}


def seed_compliance(db: Session) -> None:
    defaults = {
        "shadow_mode": {"enabled": True, "note": "M1: all outbound is draft-only until shadow review passes"},
        "quiet_hours": {"start": "21:00", "end": "09:00", "tz": "Asia/Karachi"},
        "pricing_floor": {"web_design_usd": 500, "seo_monthly_usd": 300, "note": "code-enforced floors (M2 wires to proposals)"},
    }
    for key, value in defaults.items():
        if not db.get(Setting, key):
            db.add(Setting(key=key, value=value, version=1))

    objections = [
        ("price", "It's too expensive.",
         "I understand — most clients felt the same until they saw the return. "
         "Can I show you what {business_name} could gain in 90 days before we talk price?"),
        ("timing", "Not right now / call me later.",
         "Totally fair. When would be a better time — and would a quick 2-minute "
         "audit of {business_name}'s online presence be useful in the meantime?"),
        ("trust", "How do I know you're legit?",
         "Good question. Here's my portfolio and two recent client results — "
         "no payment until you approve the plan in writing."),
        ("diy", "We handle marketing ourselves.",
         "Respect. Most teams I talk to do — I usually find 2-3 gaps in 10 minutes "
         "that are worth fixing. Want the free audit?"),
        ("competitor", "We already have an agency.",
         "Great — then you know what good looks like. I offer a free second-opinion "
         "audit; if your agency is solid, I'll tell you so."),
    ]
    for category, text, template in objections:
        exists = db.query(Objection).filter(Objection.objection_text == text).first()
        if not exists:
            db.add(Objection(category=category, objection_text=text,
                             response_template=template))
    db.commit()
    db.add(AuditLog(agent="compliance", action="seed",
                    decision="defaults + objection library seeded",
                    result="ok", ts=utcnow()))
    db.commit()
