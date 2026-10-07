"""M1 tasks. Every task: idempotent, bounded retries, no silent loss.
The daily routine runs the 7-agent pipeline in SHADOW mode: research -> verify
-> score -> prioritize -> draft outreach. Nothing sends without human approval."""
from celery import states

from .celery_app import celery


@celery.task(bind=True, max_retries=3, name="worker.tasks.healthcheck")
def healthcheck(self):
    """Heartbeat: proves worker + broker + (later) DB are alive."""
    try:
        return {"status": "ok", "task": "healthcheck"}
    except Exception as exc:  # noqa: BLE001
        self.update_state(state=states.FAILURE, meta={"error": str(exc)})
        raise


@celery.task(bind=True, max_retries=1, name="worker.tasks.daily_routine")
def daily_routine(self):
    """M1 shadow routine: full pipeline, draft-only, fully audited."""
    from app.agents.registry import run_agent, seed_all
    from app.db import SessionLocal
    from app.models import Lead

    db = SessionLocal()
    try:
        seed_all(db)
        steps = []
        # 1-2. verify + score anything new
        new_leads = db.query(Lead).filter(
            Lead.status.in_(["NEW_LEAD", "RESEARCHED"])).limit(25).all()
        for lead in new_leads:
            steps.append(("verify", run_agent(db, "verify", "verify_lead",
                                             {"lead_id": lead.id})["status"]))
        scored = db.query(Lead).filter(
            Lead.status.in_(["VERIFIED", "NEEDS_REVIEW"])).limit(25).all()
        for lead in scored:
            steps.append(("score", run_agent(db, "score", "score_lead",
                                             {"lead_id": lead.id})["status"]))
        # 3. prioritize -> queue
        queue = run_agent(db, "prioritize", "build_queue", {"limit": 10})
        # 4. draft outreach for top 3 (shadow: drafts + approval requests only)
        top = (queue.get("queue") or [])[:3]
        drafts = 0
        for item in top:
            r = run_agent(db, "outreach", "draft",
                          {"lead_id": item["lead_id"], "channel": "email"})
            if r.get("status") == "drafted":
                drafts += 1
        summary = {"steps": len(steps), "queue_size": len(queue.get("queue", [])),
                   "drafts": drafts, "shadow": True}
        return {"status": "ok", "task": "daily_routine", **summary}
    except Exception as exc:  # noqa: BLE001
        self.update_state(state=states.FAILURE, meta={"error": str(exc)})
        raise
    finally:
        db.close()
