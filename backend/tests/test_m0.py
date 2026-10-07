"""M0 verification: health, kill switch gate, approval lifecycle hardening.
Run: DATABASE_URL=sqlite:///./test.db pytest -q"""
import os

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_m0.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()  # ensure tables exist even when lifespan isn't triggered
client = TestClient(app)
client.headers["X-API-Key"] = "test-key"


def test_health_ok():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert "db" in r.json()
    assert r.json()["db"] == "ok"


def test_kill_switch_blocks_and_resumes():
    # gate open initially (or resume first to be safe)
    client.post("/v1/kill-switch/resume")
    assert client.get("/v1/outbound/demo").status_code == 200

    r = client.post("/v1/kill-switch", json={"reason": "test stop"})
    assert r.status_code == 200
    assert r.json()["active"] is True

    blocked = client.get("/v1/outbound/demo")
    assert blocked.status_code == 423  # Locked by kill switch

    r = client.post("/v1/kill-switch/resume")
    assert r.json()["active"] is False
    assert client.get("/v1/outbound/demo").status_code == 200


def test_approval_lifecycle_happy_path():
    payload = {"to": "lead-123", "subject": "hello", "body": "test"}
    c = client.post("/v1/approvals", json={"action": "send_outreach", "payload": payload})
    assert c.status_code == 200
    aid, phash = c.json()["id"], c.json()["payload_hash"]

    d = client.post(f"/v1/approvals/{aid}/decide", json={"decision": "approved"})
    assert d.json()["status"] == "APPROVED"

    e = client.post(f"/v1/approvals/{aid}/execute", json={"payload": payload})
    assert e.json()["status"] == "EXECUTED"


def test_approval_payload_change_invalidates():
    payload = {"amount": 100, "currency": "USD"}
    c = client.post("/v1/approvals", json={"action": "issue_invoice", "payload": payload})
    aid = c.json()["id"]
    client.post(f"/v1/approvals/{aid}/decide", json={"decision": "approved"})

    tampered = {"amount": 10000, "currency": "USD"}  # attacker edits after approval
    e = client.post(f"/v1/approvals/{aid}/execute", json={"payload": tampered})
    assert e.status_code == 409
    assert "re-request" in e.json()["detail"]


def test_approval_execute_is_idempotent():
    payload = {"x": 1}
    c = client.post("/v1/approvals", json={"action": "demo", "payload": payload})
    aid = c.json()["id"]
    client.post(f"/v1/approvals/{aid}/decide", json={"decision": "approved"})
    e1 = client.post(f"/v1/approvals/{aid}/execute", json={"payload": payload})
    e2 = client.post(f"/v1/approvals/{aid}/execute", json={"payload": payload})
    assert e1.json()["execution"] == "executed"
    # second execute must not re-execute (already EXECUTED -> 409, or idempotent return)
    assert e2.status_code in (200, 409)


def test_audit_log_is_read_only():
    # no update/delete endpoints may exist (404 or 405 both prove it)
    assert client.put("/v1/audit-log/abc", json={}).status_code in (404, 405)
    assert client.delete("/v1/audit-log/abc").status_code in (404, 405)
    r = client.get("/v1/audit-log?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_correlation_id_propagates():
    r = client.get("/v1/health", headers={"X-Correlation-ID": "test-123"})
    assert r.headers["X-Correlation-ID"] == "test-123"


def test_api_key_gate():
    from fastapi.testclient import TestClient as TC
    anon = TC(app)  # no API key header
    assert anon.get("/v1/health").status_code == 200  # health stays open
    assert anon.get("/v1/agents").status_code == 401  # protected: denied
    assert anon.get("/v1/agents", headers={"X-API-Key": "wrong"}).status_code == 401
    assert anon.get("/v1/agents", headers={"X-API-Key": "test-key"}).status_code == 200
