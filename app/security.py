"""HMAC-SHA256 signing (webhook connector and job callbacks) and secret redaction."""
import hashlib
import hmac
from typing import Any

SECRET_HINTS = ("secret", "token", "password", "key", "authorization", "credential")


def sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(secret, body), signature)


def redact(value: Any) -> Any:
    """Mask every value in a dict whose key looks secret. Used before anything is stored or logged."""
    if isinstance(value, dict):
        return {k: ("***" if any(h in k.lower() for h in SECRET_HINTS) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
