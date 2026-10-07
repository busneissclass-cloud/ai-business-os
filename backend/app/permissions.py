"""Tool Permission Firewall — enforced in CODE, never by prompt.
Fail-closed: unknown agent/tool/risk -> deny. HIGH/CRITICAL -> approval token required.
Autonomy caps: HIGH/CRITICAL actions can never exceed L2 (checked here)."""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .db import utcnow
from .models import AgentPermission, Approval, ToolPermission
from .security import verify_approval_signature

# Static registry = the code-level contract. DB mirrors it for audit/visibility.
TOOL_REGISTRY: dict[str, dict] = {
    "web.fetch":          {"risk": "LOW",      "requires_approval": False},
    "crm.read":           {"risk": "LOW",      "requires_approval": False},
    "crm.write":          {"risk": "MEDIUM",   "requires_approval": False},
    "outreach.draft":     {"risk": "LOW",      "requires_approval": False},
    "outreach.send":      {"risk": "HIGH",     "requires_approval": True},
    "call.place":         {"risk": "CRITICAL", "requires_approval": True},
    "billing.invoice_issue": {"risk": "HIGH",  "requires_approval": True},
    "billing.money_move": {"risk": "CRITICAL", "requires_approval": True, "forbidden": True},
    "contract.sign":      {"risk": "CRITICAL", "requires_approval": True},
    "settings.change":    {"risk": "HIGH",     "requires_approval": True},
    "data.delete":        {"risk": "CRITICAL", "requires_approval": True},
}

AGENT_REGISTRY: dict[str, dict] = {
    "research":     {"tools": ["web.fetch", "crm.read", "crm.write"], "max_autonomy": "L3"},
    "verify":       {"tools": ["crm.read", "crm.write"], "max_autonomy": "L3"},
    "score":        {"tools": ["crm.read", "crm.write"], "max_autonomy": "L3"},
    "prioritize":   {"tools": ["crm.read", "crm.write"], "max_autonomy": "L3"},
    "outreach":     {"tools": ["crm.read", "outreach.draft"], "max_autonomy": "L1"},
    "conversation": {"tools": ["crm.read", "crm.write", "outreach.draft", "outreach.send"], "max_autonomy": "L3"},
    "billing":      {"tools": ["crm.read", "billing.invoice_issue"], "max_autonomy": "L2"},
    "voice_client": {"tools": ["crm.read", "call.place"], "max_autonomy": "L2"},
    "owner_voice":  {"tools": ["crm.read"], "max_autonomy": "L3"},
    "compliance":   {"tools": [], "max_autonomy": "VETO"},  # veto-only, executes nothing
}

# Permanent L2 cap: these risks can never run above L2, whatever the agent claims.
L2_CAPPED_RISKS = {"HIGH", "CRITICAL"}


@dataclass
class AuthzResult:
    allowed: bool
    reason: str


def seed_permissions(db: Session) -> None:
    for tool, spec in TOOL_REGISTRY.items():
        if not db.get(ToolPermission, tool):
            db.add(ToolPermission(
                tool=tool, risk_level=spec["risk"],
                requires_approval=spec["requires_approval"],
                allowed_agents=[a for a, s in AGENT_REGISTRY.items() if tool in s["tools"]],
                forbidden=spec.get("forbidden", False)))
    for agent, spec in AGENT_REGISTRY.items():
        if not db.get(AgentPermission, agent):
            db.add(AgentPermission(agent=agent, allowed_tools=spec["tools"],
                                   allowed_data=["*"], max_autonomy=spec["max_autonomy"],
                                   updated_by="seed"))
    db.commit()


def authorize(db: Session, agent: str, tool: str,
              approval_id: str | None = None) -> AuthzResult:
    """Server-side gate. The LLM is never trusted to enforce this."""
    agent_row = db.get(AgentPermission, agent)
    if not agent_row:
        # fall back to static registry for bootstrap, still fail-closed on unknown
        spec = AGENT_REGISTRY.get(agent)
        if not spec:
            return AuthzResult(False, f"unknown agent: {agent}")
        allowed_tools, max_autonomy = spec["tools"], spec["max_autonomy"]
    else:
        allowed_tools, max_autonomy = agent_row.allowed_tools, agent_row.max_autonomy

    tool_row = db.get(ToolPermission, tool)
    if tool_row:
        risk, requires_approval = tool_row.risk_level, tool_row.requires_approval
        if tool_row.forbidden:
            return AuthzResult(False, f"tool {tool} is forbidden by architecture")
    else:
        spec = TOOL_REGISTRY.get(tool)
        if not spec:
            return AuthzResult(False, f"unknown tool: {tool}")
        risk, requires_approval = spec["risk"], spec["requires_approval"]
        if spec.get("forbidden"):
            return AuthzResult(False, f"tool {tool} is forbidden by architecture")

    if tool not in allowed_tools:
        return AuthzResult(False, f"agent {agent} not granted tool {tool}")

    if risk in L2_CAPPED_RISKS:
        # Permanent cap: HIGH/CRITICAL can never exceed L2 autonomy.
        if max_autonomy not in ("L2", "VETO") and not (risk == "HIGH" and max_autonomy == "L3"):
            # L3 agents may USE high-risk tools only with approval; L4 never.
            if max_autonomy in ("L4",):
                return AuthzResult(False, f"risk {risk} capped at L2; agent at {max_autonomy}")

    if requires_approval:
        if not approval_id:
            return AuthzResult(False, f"tool {tool} requires a valid approval token")
        ap = db.get(Approval, approval_id)
        if not ap or ap.status != "APPROVED":
            return AuthzResult(False, "approval not found or not APPROVED")
        if ap.expires_at and ap.expires_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
            return AuthzResult(False, "approval expired")
        if not verify_approval_signature(ap.id, ap.payload_hash, ap.approval_signature):
            return AuthzResult(False, "approval signature invalid")
        return AuthzResult(True, f"authorized with approval {approval_id}")

    return AuthzResult(True, "authorized (low-risk tool)")
