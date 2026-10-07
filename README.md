# AI Business OS — M0 Foundation

Production-grade autonomous business operating system. This repo is the
implementation of `../ai-business-agent/ARCHITECTURE.md` (FINAL, frozen) and
`../ai-business-agent/FINAL_AUDIT.md` (build contract).

## M0 scope (this milestone)
- Docker Compose: Postgres 16 + pgvector, Redis 7, API, Celery worker + beat
- FastAPI core: health, kill switch, versioned settings, audit log (append-only),
  hardened approvals (payload-hash binding, idempotency)
- Correlation IDs on every request; UTC everywhere; PII redaction in logs
- Secret vault rules (`docs/VAULT.md`); CI runs the M0 test suite

## Run (production-like, needs Docker)
```bash
cp .env.example .env   # fill secrets
docker compose up -d
curl localhost:8000/v1/health
```

## Run (local dev, no Docker)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && DATABASE_URL=sqlite:///./aibos.db uvicorn app.main:app --reload
pytest -q
```

## M0 exit criteria
- [ ] `docker compose up` → all services healthy
- [ ] Kill switch: activate → outbound gate 423 → resume → 200 (tested)
- [ ] Approval payload tampering → 409 invalid (tested)
- [ ] Release gates 7 (backup restore) + 8 (kill switch) pass

## M0.5 hardening (done 2026-10-07)
- Tool permission firewall in code: static registry + DB mirror, `POST /v1/permissions/check`
  gate — unknown agent/tool denied, HIGH/CRITICAL require a real signed approval,
  money movement permanently forbidden, L2 autonomy caps enforced server-side.
- Trust boundary: external content scanned as data, never instructions
  (prompt injection, exfiltration, credential harvesting, social engineering,
  privilege escalation, malicious links, hidden markers) -> blocked + security event.
- Buying intent engine: signal ingestion with decay + dedup, 0-100 score separate
  from lead score, per-signal "why" explanations.
- Freshness engine: field-level verification, tier-based revalidation cadence.
- Contact verification: email (syntax/domain/MX/disposable/role) + phone
  (normalize/country hint) with honest states.
- Next-best-action engine + AI Business Brain daily brief from live data only.
- Verified: 15 new tests pass, including 3 red-team injection attacks (all blocked).

## M1 — first 7 agents (done 2026-10-07)
- Agent framework: `app/agents/base.py` — identity, permission-firewall gate on every
  tool call, compliance precheck, full audit trail, shadow-mode downgrade, kill-switch halt.
- Agent 0 Compliance: veto gate — quiet hours, opt-outs, cold-channel rules
  (cold WhatsApp blocked), shadow-mode enforcement. Seeded: quiet hours 21:00-09:00
  PKT, shadow mode ON, objection library (5), pricing floors.
- Agent 1 Research: manual + URL ingestion, name/domain/phone dedup, trust-scan
  quarantine on every external text.
- Agent 2 Verify: evidence-based verification via M0.5 engines (no vibes).
- Agent 3 Score: transparent 0-100 fit score, factor breakdown sums exactly, HOT/HIGH/MEDIUM/LOW.
- Agent 4 Prioritize: revenue-ranked queue (score x intent), with "why" per lead.
- Agent 5 Outreach: A/B drafts + approval requests; compliance precheck first;
  never sends in shadow mode.
- Agent 6 Conversation: inbound classification, objection-library drafts, instant
  permanent opt-out, graceful exits, unclear -> owner escalation.
- Daily shadow routine (Celery beat): verify -> score -> prioritize -> draft top-3.
- API: `GET /v1/agents`, `POST /v1/agents/{name}/run`, `POST /v1/agents/seed`.
- Verified: 12 new tests pass (34 total) — gates, shadow mode, quarantine,
  end-to-end shadow routine with zero sends.

## Next: M2 — pipeline agents 7-13 (meeting, proposal, negotiation, contract, payment, onboarding, delivery)
