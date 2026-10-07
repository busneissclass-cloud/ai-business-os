"""Trust boundary: ALL external content is untrusted DATA, never instructions.
Heuristic detector (v1) + quarantine. High-severity hit -> BLOCKED + security event.
This is defense-in-depth; the permission firewall remains the hard gate."""
import re

from sqlalchemy.orm import Session

from .db import utcnow
from .models import SecurityEvent

# (category, severity, patterns)
PATTERNS: list[tuple[str, str, list[str]]] = [
    ("PROMPT_INJECTION", "HIGH", [
        r"ignore.{0,40}instructions",
        r"disregard.{0,40}instructions",
        r"you are now (a|an|in)",
        r"system prompt",
        r"jailbreak", r"\bDAN\b.{0,20}mode",
        r"override (your|the) (system|developer|previous)",
        r"forget (your|all) (prior |previous )?instructions",
    ]),
    ("DATA_EXFILTRATION", "HIGH", [
        r"send (all |the )?(client|user|customer)? ?data to",
        r"exfiltrat", r"copy .* to https?://",
        r"email .* to \S+@\S+",
    ]),
    ("CREDENTIAL_REQUEST", "HIGH", [
        r"(give|send|share|reveal).{0,40}(password|api[_-]?key|secret|token|credentials)",
        r"(password|api[_-]?key).{0,20}(is|:)\s*\S+",
    ]),
    ("SOCIAL_ENGINEERING", "HIGH", [
        r"urgent.{0,40}(wire|transfer|payment)",
        r"\bceo\b.{0,40}(transfer|wire|urgent)",
        r"gift ?cards?.{0,30}(urgent|asap|immediately)",
    ]),
    ("MALICIOUS_LINK", "MEDIUM", [
        r"https?://[^\s]*\.(exe|scr|bat|msi|dll)(\?|$)",
        r"click here to (verify|confirm|claim)",
        r"https?://[^\s]*@(?!.*$)",
    ]),
    ("PRIVILEGE_ESCALATION", "HIGH", [
        r"(grant|give).{0,30}(admin|root|owner) (access|rights|permission)",
        r"disable (the )?(kill.?switch|safety|approval)",
        r"bypass (the )?(approval|permission|firewall)",
    ]),
    ("TOOL_ABUSE", "MEDIUM", [
        r"run (this|the) (command|script|code)",
        r"execute .{0,20}(shell|bash|powershell)",
    ]),
    ("IDENTITY_IMPERSONATION", "MEDIUM", [
        r"i am (the )?(owner|admin|abdul)(,| and|;)",
        r"this is (the )?(owner|ceo) speaking",
    ]),
]

_COMPILED = [(c, s, [re.compile(p, re.IGNORECASE) for p in ps]) for c, s, ps in PATTERNS]
_HIDDEN_MARKERS = re.compile(r"[\u200b-\u200f\u202a-\u202e]|\[SYSTEM\]|<!--")


def scan_external_content(db: Session, source: str, text: str) -> dict:
    """Returns verdict: clean | suspicious | blocked. Logs medium+ hits."""
    hits: list[dict] = []
    lowered = text or ""
    if _HIDDEN_MARKERS.search(lowered):
        hits.append({"category": "PROMPT_INJECTION", "severity": "HIGH",
                     "match": "hidden instruction markers"})
    for category, severity, regexes in _COMPILED:
        for rx in regexes:
            m = rx.search(lowered)
            if m:
                hits.append({"category": category, "severity": severity,
                             "match": m.group(0)[:120]})
                break  # one hit per category is enough

    verdict = "clean"
    if any(h["severity"] == "HIGH" for h in hits):
        verdict = "blocked"
    elif hits:
        verdict = "suspicious"

    if verdict != "clean":
        sev = "HIGH" if verdict == "blocked" else "MEDIUM"
        db.add(SecurityEvent(
            category=hits[0]["category"], source=source,
            detail={"hits": hits, "text_excerpt": (text or "")[:500]},
            severity=sev,
            action_taken="blocked" if verdict == "blocked" else "flagged",
            ts=utcnow()))
        db.commit()
    return {"verdict": verdict, "hits": hits}
