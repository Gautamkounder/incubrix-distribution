"""The IncuBrix connector contract (Appendix A): same methods, manifest and error codes for every connector."""
import re
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, Field

from app.config import Settings
from app.errors import AppError, ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

LINK_RE = re.compile(r"https?://\S+")


class Surface(BaseModel):
    key: str
    content_types: list[str] = Field(default_factory=list)
    spec: dict[str, Any] = Field(default_factory=dict)


class Manifest(BaseModel):
    key: str
    version: str
    tier: str  # native | protocol | bridge | feed | assisted
    auth: str  # oauth2 | api_key | bot_token | none
    surfaces: list[Surface]
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    error_map: dict[str, str] = Field(default_factory=dict)
    instance_param: str | None = None


def load_manifest(path: Path) -> Manifest:
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    for code in manifest.error_map.values():
        ErrorCode(code)  # a typo in a manifest fails at startup, not in production
    return manifest


class Connector:
    """Methods return results only. They never write to IncuBrix's database; the runtime does that."""

    def __init__(self, manifest: Manifest, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.manifest = manifest
        self.settings = settings
        self.transport = transport

    @property
    def key(self) -> str:
        return self.manifest.key

    # ---- contract methods ----
    def validate(self, rendition: Rendition, destination: Destination, connection: dict) -> dict:
        spec = self._spec(destination)
        violations: list[dict] = []
        title_max, body_max = spec.get("title_max_chars"), spec.get("body_max_chars")
        if title_max and len(rendition.title) > title_max:
            violations.append({"field": "title", "reason": "too_long", "limit": title_max, "actual": len(rendition.title)})
        if body_max and len(rendition.body) > body_max:
            violations.append({"field": "body", "reason": "too_long", "limit": body_max, "actual": len(rendition.body)})
        if spec.get("links_allowed") is False and LINK_RE.search(rendition.body):
            violations.append({"field": "body", "reason": "links_not_allowed"})
        return {"ok": not violations, "violations": violations}

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        raise self._unsupported("publish")

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        raise self._unsupported("get_status")

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        raise self._unsupported("delete")

    def fetch_metrics(self, platform_post_id: str, connection: dict, since: str | None = None) -> dict:
        raise self._unsupported("fetch_metrics")

    def refresh_auth(self, connection: dict) -> dict:
        raise self._unsupported("refresh_auth")

    def build_assist_pack(self, rendition: Rendition, destination: Destination) -> dict:
        raise self._unsupported("build_assist_pack")

    # ---- helpers ----
    def _spec(self, destination: Destination) -> dict:
        surfaces = {s.key: s for s in self.manifest.surfaces}
        surface = surfaces.get(destination.surface or "") or self.manifest.surfaces[0]
        return {**surface.spec, **destination.config.get("spec", {})}  # per-destination override = config, not code

    def _unsupported(self, method: str) -> AppError:
        return AppError(ErrorCode.METHOD_NOT_SUPPORTED, f"Connector '{self.key}' does not support {method}",
                        details={"connector": self.key, "method": method})

    def error_from_response(self, resp: httpx.Response) -> ConnectorError:
        """Map a platform HTTP error to the shared error codes using the manifest's error_map."""
        status = resp.status_code
        mapped = self.manifest.error_map.get(str(status))
        if mapped:
            code = ErrorCode(mapped)
        elif status == 429:
            code = ErrorCode.PLATFORM_RATE_LIMIT
        elif status in (401, 403):
            code = ErrorCode.CONNECTION_AUTH_EXPIRED
        elif status >= 500:
            code = ErrorCode.PLATFORM_UNAVAILABLE
        else:
            code = ErrorCode.PLATFORM_CONTENT_REJECTED
        details: dict[str, Any] = {"platform_status": status, "platform_message": resp.text[:300]}
        retry_after = resp.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            details["retry_after_s"] = int(retry_after)  # back off until the platform's reset time
        return ConnectorError(code, f"{self.key} returned HTTP {status}", details=details)
