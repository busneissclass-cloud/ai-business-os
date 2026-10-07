"""Agent 5 — Outreach. Drafts, never sends, in shadow mode.
Pipeline per draft: compliance precheck -> template + personalization ->
A/B variant -> stored draft -> approval request. Sending happens ONLY through
the hardened approval execute path, and only when shadow mode is off."""
from __future__ import annotations

from .base import AgentBlocked, BaseAgent, shadow_mode_on
from ..models import Approval, Lead, OutreachDraft
from ..security import payload_hash
from ..db import utcnow
from datetime import timedelta

TEMPLATES = {
    "email": {
        "subject": "Quick idea for {business_name}",
        "body": ("Hi {name},\n\nI looked at {business_name}'s online presence and "
                 "spotted {hook} — most businesses in your space miss this.\n\n"
                 "I help companies fix exactly this. Worth a 10-minute call this week?\n\n"
                 "Best,\nAbdul Rehman"),
    },
    "whatsapp": {
        "body": ("Assalam-o-Alaikum, this is Abdul Rehman. I noticed {hook} on "
                 "{business_name}'s page. I help businesses fix this — "
                 "can I share a free 2-minute audit?"),
    },
    "linkedin": {
        "body": ("Hi {name}, came across {business_name} and noticed {hook}. "
                 "I help companies turn that into more customers. "
                 "Open to a quick chat? — Abdul"),
    },
}

HOOKS = [
    "a few quick wins on your website",
    "your Google Business profile could rank higher",
    "your landing page may be losing mobile visitors",
]


class OutreachAgent(BaseAgent):
    name = "outreach"
    prompt_version = "outreach-v1"

    def execute(self, task: str, params: dict) -> dict:
        if task == "draft":
            return self._draft(params.get("lead_id", ""), params.get("channel", "email"))
        if task == "draft_batch":
            return self._draft_batch(params.get("lead_ids", []),
                                     params.get("channel", "email"))
        return {"status": "unknown task", "task": task}

    def _draft_batch(self, lead_ids: list[str], channel: str) -> dict:
        return {"drafts": [self._draft(lid, channel) for lid in lead_ids]}

    def _draft(self, lead_id: str, channel: str) -> dict:
        self.check_tool("outreach.draft")
        self.check_tool("crm.read")
        lead = self.db.get(Lead, lead_id)
        if not lead:
            return {"status": "unknown_lead"}
        if channel not in TEMPLATES:
            return {"status": "unknown_channel", "channel": channel}

        # compliance FIRST — before a single word is written
        pre = self.compliance_check("outreach.send",
                                    {"channel": channel, "to": lead.business_name})
        if not pre["allowed"]:
            self.audit("draft:blocked",
                       decision=f"compliance veto: {'; '.join(pre['reasons'])}",
                       result="blocked")
            return {"status": "blocked",
                    "reason": "; ".join(pre["reasons"])}

        tpl = TEMPLATES[channel]
        hook = HOOKS[hash(lead_id) % len(HOOKS)]
        tokens = {"business_name": lead.business_name, "name": "there", "hook": hook}
        bodies = {}
        for variant in ("A", "B"):
            body = tpl["body"].format(**tokens)
            if variant == "B":
                # short variant for A/B testing
                body = body.split("\n\n")[0] + "\n\nWorth a quick chat? — Abdul"
            bodies[variant] = body

        drafts = []
        for variant, body in bodies.items():
            d = OutreachDraft(
                lead_id=lead_id, channel=channel, variant=variant,
                subject=tpl.get("subject", "").format(**tokens) or None,
                body=body,
                personalization={"hook": hook, "tier": lead.tier,
                                 "intent": lead.buying_intent_level},
                status="draft")
            self.db.add(d)
            drafts.append(d)
        self.db.commit()

        # request approval for variant A (human decides; shadow mode = draft stays draft)
        payload = {"draft_id": drafts[0].id, "lead_id": lead_id,
                   "channel": channel, "variant": "A"}
        ap = Approval(action="outreach.send", payload=payload,
                      payload_hash=payload_hash(payload),
                      requested_by="owner", requested_agent="outreach",
                      status="PENDING", risk_level="HIGH", autonomy_level="L2",
                      expires_at=utcnow() + timedelta(hours=48))
        self.db.add(ap)
        drafts[0].approval_id = ap.id
        if lead.status == "PRIORITIZED":
            lead.status = "CONTACTED"
        self.db.commit()

        shadow = shadow_mode_on(self.db)
        self.audit("draft",
                   decision=(f"2 variants for {lead.business_name} via {channel}; "
                             f"approval {ap.id} requested; "
                             f"{'SHADOW: send suppressed' if shadow else 'awaiting human approval'}"),
                   output={"draft_ids": [d.id for d in drafts],
                           "approval_id": ap.id},
                   approval_required=True, approval_status="PENDING")
        return {"status": "drafted", "lead_id": lead_id, "channel": channel,
                "draft_ids": [d.id for d in drafts], "approval_id": ap.id,
                "shadow_mode": shadow,
                "compliance_notes": pre["reasons"]}
