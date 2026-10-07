"""Security helpers: PII redaction, payload hashing, approval signatures."""
import hashlib
import hmac
import json
import re

from .config import settings

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")


def redact_pii(text: str) -> str:
    """Mask emails/phones before anything hits logs."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[email redacted]", text)
    text = _PHONE_RE.sub("[phone redacted]", text)
    return text


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def sign_approval(approval_id: str, phash: str) -> str:
    msg = f"{approval_id}:{phash}".encode()
    return hmac.new(settings.API_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def verify_approval_signature(approval_id: str, phash: str, signature: str) -> bool:
    expected = sign_approval(approval_id, phash)
    return hmac.compare_digest(expected, signature or "")
