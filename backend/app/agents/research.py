"""Agent 1 — Research. Discovery -> normalized, deduped, evidence-backed leads.
Every external text is trust-scanned BEFORE it can influence anything.
M1 adapters: manual (user/API supplied), url (fetch + extract). More sources in M2."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .base import AgentBlocked, BaseAgent
from ..models import Lead
from ..trust import scan_external_content

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        d = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
        return d[4:] if d.startswith("www.") else d or None
    except Exception:
        return None


def _norm_phone(p: str | None) -> str | None:
    if not p:
        return None
    d = re.sub(r"\D", "", p)
    return f"+{d}" if 7 <= len(d) <= 15 else None


class ResearchAgent(BaseAgent):
    name = "research"
    prompt_version = "research-v1"

    def execute(self, task: str, params: dict) -> dict:
        if task == "ingest_manual":
            return self._ingest(params.get("candidates", []), source="manual")
        if task == "ingest_url":
            return self._ingest_url(params.get("url", ""))
        return {"status": "unknown task", "task": task}

    def _ingest(self, candidates: list[dict], source: str) -> dict:
        self.check_tool("web.fetch")
        self.check_tool("crm.write")
        created, skipped = 0, 0
        for c in candidates:
            name = (c.get("business_name") or "").strip()
            if not name:
                skipped += 1
                continue
            # trust-scan any free text that came with the candidate
            blob = " ".join(str(c.get(k, "")) for k in ("notes", "description", "about"))
            if blob.strip():
                verdict = scan_external_content(self.db, f"research:{source}", blob)
                if verdict["verdict"] == "blocked":
                    self.audit("ingest:quarantined",
                               decision=f"candidate '{name}' quarantined: {verdict['hits'][0]['category']}",
                               result="blocked")
                    skipped += 1
                    continue
            if self._dedup_hit(name, c.get("website"), c.get("phone")):
                skipped += 1
                continue
            lead = Lead(business_name=name, status="NEW_LEAD",
                        website=c.get("website"), email=c.get("email"),
                        phone=c.get("phone"), notes=c.get("notes"))
            self.db.add(lead)
            created += 1
        self.db.commit()
        self.audit("ingest", decision=f"source={source} created={created} skipped={skipped}")
        return {"created": created, "skipped": skipped, "source": source}

    def _ingest_url(self, url: str) -> dict:
        """Fetch a page, extract a candidate, trust-scan everything."""
        self.check_tool("web.fetch")
        if not url:
            raise AgentBlocked("no url provided")
        try:
            import httpx
            resp = httpx.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "AIBusinessOS-research/1.0"})
            resp.raise_for_status()
            text = resp.text
        except Exception as e:  # noqa: BLE001
            self.audit("ingest_url:fetch_failed", decision=str(e)[:300], result="error")
            return {"status": "fetch_failed", "url": url, "error": str(e)[:200]}

        verdict = scan_external_content(self.db, f"url:{url}", text[:20000])
        if verdict["verdict"] == "blocked":
            self.audit("ingest_url:quarantined",
                       decision=f"blocked: {verdict['hits'][0]['category']}", result="blocked")
            return {"status": "quarantined", "url": url,
                    "reason": verdict["hits"][0]["category"]}

        # naive extraction (honest: best-effort, evidence-linked)
        title = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
        emails = list(dict.fromkeys(EMAIL_RE.findall(text)))[:3]
        phones = list(dict.fromkeys(PHONE_RE.findall(text)))[:3]
        name = (title.group(1).strip()[:120] if title else _domain(url)) or "Unknown"
        candidate = {"business_name": name, "website": url,
                     "email": emails[0] if emails else None,
                     "phone": phones[0] if phones else None,
                     "notes": f"extracted from {url}"}
        return self._ingest([candidate], source=f"url:{_domain(url)}")

    def _dedup_hit(self, name: str, website: str | None, phone: str | None) -> bool:
        # autoflush is off: flush pending adds so the query sees this batch
        self.db.flush()
        domain = _domain(website)
        norm = _norm_phone(phone)
        for lead in self.db.query(Lead).all():
            if lead.business_name.lower() == name.lower():
                return True
            if domain and lead.website and _domain(lead.website) == domain:
                return True
            if norm and lead.phone and _norm_phone(lead.phone) == norm:
                return True
        return False
