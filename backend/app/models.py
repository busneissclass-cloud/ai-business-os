"""M0 data model. UUIDs as strings for SQLite/Postgres portability.
Money uses NUMERIC (never float). Audit log is append-only (no update/delete API)."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


def new_id() -> str:
    return uuid.uuid4().hex


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """Append-only. No UPDATE/DELETE endpoints exist by design."""
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(128))
    input: Mapped[dict | None] = mapped_column("input", JSON, nullable=True)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tools_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approval_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    approval_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class Approval(Base):
    """Hardened lifecycle. Approval valid ONLY for exact payload_hash."""
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128))
    requested_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    autonomy_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="v1")
    approval_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    execution_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(128))
    actor: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="IN_PROGRESS")
    result_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    """M0.5: core + buying intent columns. Full CRM schema lands in M1."""
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    business_name: Mapped[str] = mapped_column(String(256), index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="NEW_LEAD", index=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)  # HOT|HIGH|MEDIUM|LOW
    lead_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buying_intent_score: Mapped[int] = mapped_column(Integer, default=0)
    buying_intent_level: Mapped[str] = mapped_column(String(16), default="VERY_LOW")
    buying_intent_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ---------------- M0.5: permission firewall, trust boundary, intelligence ----------------

class AgentPermission(Base):
    __tablename__ = "agent_permissions"
    agent: Mapped[str] = mapped_column(String(64), primary_key=True)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list)
    allowed_data: Mapped[list] = mapped_column(JSON, default=list)
    max_autonomy: Mapped[str] = mapped_column(String(8), default="L1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str] = mapped_column(String(128), default="system")


class ToolPermission(Base):
    __tablename__ = "tool_permissions"
    tool: Mapped[str] = mapped_column(String(128), primary_key=True)
    risk_level: Mapped[str] = mapped_column(String(16))  # LOW|MEDIUM|HIGH|CRITICAL
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_agents: Mapped[list] = mapped_column(JSON, default=list)
    forbidden: Mapped[bool] = mapped_column(Boolean, default=False)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    action_taken: Mapped[str] = mapped_column(String(64), default="blocked")
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class BuyingIntentSignal(Base):
    __tablename__ = "buying_intent_signals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(32), ForeignKey("leads.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(64))
    signal_source: Mapped[str] = mapped_column(String(128))
    signal_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signal_strength: Mapped[int] = mapped_column(Integer, default=3)
    evidence_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confidence: Mapped[str] = mapped_column(String(32), default="INFERENCE")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadFreshness(Base):
    __tablename__ = "lead_freshness"
    lead_id: Mapped[str] = mapped_column(String(32), ForeignKey("leads.id"), primary_key=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # {field: {verified_at, source}}
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0)
    freshness_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")


class ContactVerification(Base):
    __tablename__ = "contact_verifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("leads.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # email | phone
    value: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32))  # VALID|LIKELY_VALID|RISKY|INVALID|UNKNOWN
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NextBestAction(Base):
    __tablename__ = "next_best_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("leads.id"), nullable=True)
    action: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    confidence: Mapped[int] = mapped_column(Integer, default=50)
    expected_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    required_approval: Mapped[str] = mapped_column(String(16), default="L2")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------- M1: agents ----------------

class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    task: Mapped[str] = mapped_column(String(128))
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tools_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(32), ForeignKey("leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32))  # email | whatsapp | linkedin
    variant: Mapped[str] = mapped_column(String(8), default="A")
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    personalization: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    approval_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(32), ForeignKey("leads.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))  # inbound | outbound
    channel: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Objection(Base):
    __tablename__ = "objections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    category: Mapped[str] = mapped_column(String(64), index=True)
    objection_text: Mapped[str] = mapped_column(Text)
    response_template: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="en")


class OptOut(Base):
    __tablename__ = "opt_outs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    value: Mapped[str] = mapped_column(String(256), index=True)  # email/phone/handle
    channel: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LeadScoreEvent(Base):
    __tablename__ = "lead_score_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(32), ForeignKey("leads.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(String(16))
    factors: Mapped[dict] = mapped_column(JSON)  # factor -> {value, weight, contribution}
    model_version: Mapped[str] = mapped_column(String(32), default="score-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
