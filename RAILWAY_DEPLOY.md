# Easiest way live — Railway.app (no server management)

**Cost:** ~$5/month (Postgres + Redis + API included). **Time:** ~15 minutes.

## Steps

1. **Code GitHub par push karein** (neeche "GitHub push" dekhein — ya mujhe ijazat dein, main kar dun).
2. **Railway.app** par account banayein (GitHub se login).
3. **New Project → Deploy from GitHub repo** → `ai-business-os` select karein.
4. Service settings mein **Root Directory = `backend`** set karein.
5. **+ New → Database → Postgres** add karein. Phir **+ New → Database → Redis** add karein.
   Railway khud `DATABASE_URL` aur `REDIS_URL` bana ke web service mein daal dega.
6. Web service ke **Variables** mein add karein:
   - `API_SECRET` = koi lambi random string (openssl rand -hex 32)
   - `API_KEY` = koi lambi random string (yeh aapki API ki key hai — har request mein `X-API-Key` header mein jayegi)
   - `ENV` = production
7. **Deploy** — 2-3 minute mein `https://aibos-....up.railway.app` live.

## Daily routine (automatic)

2 aur services banayein — same repo, Root Directory `backend`:

| Service | Start command |
|---|---|
| `worker` | `celery -A worker.celery_app.celery worker --loglevel=info --concurrency=2` |
| `beat` | `celery -A worker.celery_app.celery beat --loglevel=info` |

Dono ko Postgres/Redis variables se connect karein (Railway mein "shared variables").
Beat roz subah 9 baje routine chalayega: verify → score → prioritize → drafts.
**Shadow mode ON rahega** — kuch bhi aapki approval ke baghair nahi bhejega.

## GitHub push

```bash
cd ~/workspace/ai-business-os
git init && git add -A && git commit -m "AI Business OS M1"
gh repo create ai-business-os --public --source=. --push
```

`.env` kabhi commit nahi hota (gitignore mein hai) — secrets sirf Railway variables mein.
