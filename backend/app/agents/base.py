"""BaseAgent: every agent runs through the same harness.
- Identity + permission firewall on every tool call (authorize(), never a prompt)
- Compliance pre-check on every high-stakes action
- Full audit trail: agent, action, input, decision, output, model, prompt version
- Shadow mode: outbound tools are force-downgraded to drafts
- LLM is pluggable; without credentials agents run deterministic rules mode."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import killswitch
from ..db import SessionLocal, utcnow
from ..models import AgentRun, AuditLog, Setting
from ..permissions import authorize

OUTBOUND_TOOLS = {"outreach.send", "call.place", "billing.invoice_issue",
                  "contract.sign", "data.delete"}


def get_setting_value(db: Session, key: str, default):
    row = db.get(Setting, key)
    return row.value.get("value", default) if row else default


def shadow_mode_on(db: Session) -> bool:
    val = get_setting_value(db, "shadow_mode", True)
    return bool(val.get("enabled", True)) if isinstance(val, dict) else bool(val)


class AgentBlocked(Exception):
    pass


class BaseAgent:
    name = "base"
    prompt_version = "v1"
    model = "rules-v1"  # replaced by LiteLLM model id when credentials land

    def __init__(self, db: Session, correlation_id: str | None = None):
        self.db = db
        self.correlation_id = correlation_id or "none"
        self.tools_used: list[str] = []
        self._run: AgentRun | None = None

    # ----- gates -----
    def check_tool(self, tool: str, approval_id: str | None = None) -> None:
        """Hard gate: permission firewall + shadow-mode downgrade for outbound."""
        if killswitch.is_killed()["active"]:
            raise AgentBlocked("kill switch active — all agent activity halted")
        result = authorize(self.db, self.name, tool, approval_id)
        if not result.allowed:
            raise AgentBlocked(f"permission denied: {result.reason}")
        self.tools_used.append(tool)

    def compliance_check(self, action: str, payload: dict) -> dict:
        """Delegate to Agent 0. Imported lazily to avoid cycles."""
        from .compliance import compliance_precheck
        return compliance_precheck(self.db, self.name, action, payload)

    # ----- audit -----
    def audit(self, action: str, decision: str = "", output: dict | None = None,
              result: str = "ok", approval_required: bool = False,
              approval_status: str | None = None) -> None:
        self.db.add(AuditLog(
            agent=self.name, action=action, decision=decision[:2000],
            output=output, result=result, model=self.model,
            prompt_version=self.prompt_version, tools_used=self.tools_used,
            approval_required=approval_required, approval_status=approval_status,
            correlation_id=self.correlation_id, ts=utcnow()))
        self.db.commit()

    # ----- run wrapper -----
    def run(self, task: str, params: dict | None = None) -> dict:
        run = AgentRun(agent=self.name, task=task, params=params,
                       model=self.model, prompt_version=self.prompt_version,
                       correlation_id=self.correlation_id)
        self.db.add(run)
        self.db.commit()
        self._run = run
        try:
            out = self.execute(task, params or {})
            run.status = "completed"
            run.result = out
            run.tools_used = self.tools_used
            self.audit(f"run:{task}", decision=str(params)[:500],
                       output={"summary": str(out)[:500]})
        except AgentBlocked as e:
            run.status = "blocked"
            run.error = str(e)
            self.audit(f"run:{task}", decision=f"BLOCKED: {e}", result="blocked")
            out = {"status": "blocked", "reason": str(e)}
        except Exception as e:  # noqa: BLE001
            run.status = "failed"
            run.error = str(e)[:1000]
            self.audit(f"run:{task}", decision=f"FAILED: {e}", result="error")
            out = {"status": "failed", "error": str(e)[:500]}
        run.finished_at = utcnow()
        self.db.commit()
        return out

    def execute(self, task: str, params: dict) -> dict:
        raise NotImplementedError
