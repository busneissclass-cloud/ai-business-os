"""Contact Verification Engine. Honest states — never 'guaranteed deliverable'.
Email: syntax -> domain -> MX (dnspython; UNKNOWN if DNS unavailable) ->
       disposable -> role-account. Phone: normalize -> country hint -> format."""
import re

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
DISPOSABLE = {"mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
              "yopmail.com", "trashmail.com", "fakeinbox.com"}
ROLE_PREFIXES = {"info", "sales", "support", "admin", "contact", "hello", "team",
                 "marketing", "billing", "help", "office"}
COUNTRY_HINTS = {"92": "PK", "1": "US/CA", "44": "UK", "971": "UAE", "966": "SA",
                 "974": "QA", "61": "AU"}


def verify_email(value: str) -> dict:
    v = (value or "").strip().lower()
    checks: dict = {}
    if not EMAIL_RE.match(v):
        return {"kind": "email", "value": value, "status": "INVALID",
                "confidence": 95, "checks": {"syntax": False}}
    checks["syntax"] = True
    local, domain = v.rsplit("@", 1)
    checks["domain"] = "." in domain
    # MX check — real DNS when available
    try:
        import dns.resolver
        mx = dns.resolver.resolve(domain, "MX", lifetime=5)
        checks["mx"] = len(list(mx)) > 0
    except Exception:
        checks["mx"] = None  # UNKNOWN — DNS unavailable, don't guess
    checks["disposable"] = domain in DISPOSABLE
    checks["role_account"] = local in ROLE_PREFIXES

    if checks["disposable"]:
        status, conf = "RISKY", 80
    elif checks["mx"] is False:
        status, conf = "INVALID", 85
    elif checks["mx"] is None:
        status, conf = ("LIKELY_VALID", 60) if not checks["role_account"] else ("RISKY", 55)
    elif checks["role_account"]:
        status, conf = "RISKY", 65  # deliverable-ish but low engagement value
    else:
        status, conf = "VALID", 85
    return {"kind": "email", "value": v, "status": status, "confidence": conf,
            "checks": checks,
            "note": "States describe verification evidence, never guaranteed deliverability."}


def verify_phone(value: str) -> dict:
    v = (value or "").strip()
    digits = re.sub(r"\D", "", v)
    checks: dict = {}
    if not (7 <= len(digits) <= 15):
        return {"kind": "phone", "value": value, "status": "INVALID",
                "confidence": 90, "checks": {"format": False}}
    checks["format"] = True
    normalized = "+" + digits if not v.startswith("+") else v
    checks["normalized"] = normalized
    country = None
    for prefix, cc in sorted(COUNTRY_HINTS.items(), key=lambda x: -len(x[0])):
        if digits.startswith(prefix):
            country = cc
            break
    checks["country_hint"] = country or "UNKNOWN"
    # Format-valid with plausible country -> LIKELY_VALID (line-type needs a provider)
    status = "LIKELY_VALID" if country else "UNKNOWN"
    conf = 70 if country else 40
    return {"kind": "phone", "value": v, "status": status, "confidence": conf,
            "checks": checks,
            "note": "Line-type / WhatsApp availability require a provider lookup (M-stage)."}
