# Secret Vault — M0

## Rules (non-negotiable)
1. Secrets live in env vars / a vault — NEVER in git, chat, logs, or frontend code.
2. Required secrets: `POSTGRES_PASSWORD`, `API_SECRET` (approval HMAC signing).
3. Generate: `openssl rand -hex 32`.
4. Local dev: copy `.env.example` → `.env` (git-ignored).
5. Production (VPS): put secrets in the compose `.env` file with `chmod 600`,
   owned by root. M1+: evaluate a proper vault (e.g. age/sops-encrypted env).
6. Rotation: changing `API_SECRET` invalidates outstanding approval signatures
   by design (fail-closed). Announce rotation; re-request pending approvals.

## What's NOT a secret here
- Correlation IDs, lead business data, audit metadata — logged (PII-redacted).
- PII (emails/phones) is SENSITIVE: encrypted at rest (M1), redacted in logs (now).
