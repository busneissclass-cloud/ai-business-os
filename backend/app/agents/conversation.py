"""Agent 6 — Conversation. Inbound replies: classify -> respond or escalate.
Unsubscribe/opt-out is honored INSTANTLY and permanently. Objections get a
drafted response from the library; anything unclear escalates to the owner.
Never argues, never spams, never sends without approval."""
from __future__ import annotations

import re

from .base import BaseAgent
from ..models import ConversationMessage, Lead, Objection, OptOut
from ..db import utcnow

# (classification, confidence, patterns)
INTENTS = [
    ("interested", 80, [r"\b(interested|let'?s talk|call me|send (me )?(details|proposal|quote))\b",
                        r"\b(yes|yeah|sure)\b.{0,20}(call|meet|discuss)"]),
    ("question", 75, [r"\?", r"\b(how much|price|cost|how long|timeline|process)\b"]),
    ("objection_price", 80, [r"\b(expensive|too much|can'?t afford|budget)\b"]),
    ("objection_timing", 80, [r"\b(not now|later|busy|next (month|quarter|year))\b"]),
    ("objection_trust", 75, [r"\b(scam|legit|trust|who are you|prove)\b"]),
    ("not_interested", 85, [r"\b(not interested|no thanks|don'?t (want|need|contact))\b"]),
    ("wrong_person", 85, [r"\b(wrong (person|number|email)|not (me|mine|ours))\b"]),
    ("unsubscribe", 95, [r"\b(unsubscribe|opt.?out|stop|remove me|do not (contact|email|message))\b"]),
]

OBJECTION_MAP = {"objection_price": "price", "objection_timing": "timing",
                 "objection_trust": "trust"}


class ConversationAgent(BaseAgent):
    name = "conversation"
    prompt_version = "conversation-v1"

    def execute(self, task: str, params: dict) -> dict:
        if task == "handle_inbound":
            return self._handle_inbound(params.get("lead_id", ""),
                                        params.get("channel", "email"),
                                        params.get("body", ""))
        return {"status": "unknown task", "task": task}

    def _classify(self, body: str) -> tuple[str, int]:
        text = (body or "").lower()
        for intent, conf, patterns in INTENTS:
            for p in patterns:
                if re.search(p, text):
                    return intent, conf
        return "unclear", 40

    def _handle_inbound(self, lead_id: str, channel: str, body: str) -> dict:
        self.check_tool("crm.read")
        self.check_tool("crm.write")
        lead = self.db.get(Lead, lead_id)
        if not lead:
            return {"status": "unknown_lead"}

        intent, conf = self._classify(body)
        msg = ConversationMessage(lead_id=lead_id, direction="inbound",
                                  channel=channel, body=body[:2000],
                                  classification=intent,
                                  classification_confidence=conf)
        self.db.add(msg)

        # UNSUBSCRIBE: instant, permanent, no reply drafted
        if intent == "unsubscribe":
            contact = self._contact_value(lead)
            if contact:
                self.db.add(OptOut(value=contact.lower(), channel=channel,
                                   reason="unsubscribe via conversation"))
            lead.status = "OPTED_OUT"
            self.db.commit()
            self.audit("handle_inbound",
                       decision=f"UNSUBSCRIBE honored for {lead.business_name}; opted out, no reply",
                       result="ok")
            return {"status": "opted_out", "intent": intent,
                    "reply_drafted": None,
                    "note": "contact suppressed permanently"}

        response_draft = None
        if intent == "interested":
            lead.status = "QUALIFIED"
            response_draft = ("Great — I'll send over a short proposal today. "
                              "What's the best time for a 15-minute call this week?")
        elif intent in OBJECTION_MAP:
            obj = self.db.query(Objection).filter(
                Objection.category == OBJECTION_MAP[intent]).first()
            if obj:
                response_draft = obj.response_template.format(
                    business_name=lead.business_name)
        elif intent == "question":
            response_draft = ("Good question — I'll get you the exact details. "
                              "Meanwhile, here's my portfolio so you can see the work.")
        elif intent in ("not_interested", "wrong_person"):
            lead.status = "CLOSED_LOST"
            response_draft = None  # graceful exit, no pushback
        else:  # unclear -> escalate to owner, no auto-reply
            lead.status = "NEEDS_REVIEW"

        if response_draft:
            out = ConversationMessage(lead_id=lead_id, direction="outbound",
                                      channel=channel, body=response_draft,
                                      classification="draft_reply")
            self.db.add(out)
        self.db.commit()
        self.audit("handle_inbound",
                   decision=(f"{lead.business_name}: {intent} ({conf}%) -> "
                             f"{'drafted reply' if response_draft else 'no reply'}; "
                             f"status={lead.status}"),
                   output={"intent": intent, "confidence": conf,
                           "reply_drafted": bool(response_draft)})
        return {"status": "handled", "intent": intent, "confidence": conf,
                "reply_drafted": response_draft, "lead_status": lead.status,
                "note": "replies are drafts; sending needs approval (shadow: suppressed)"}

    @staticmethod
    def _contact_value(lead: Lead) -> str | None:
        return lead.email or lead.phone
