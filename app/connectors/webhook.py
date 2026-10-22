"""Generic signed webhook: send the post to any partner site, signed with HMAC-SHA256."""
import json

import httpx

from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition
from app.security import sign


class WebhookConnector(Connector):
    def _endpoint_and_secret(self, connection: dict) -> tuple[str, str]:
        endpoint, secret = connection.get("endpoint"), connection.get("secret")
        if not endpoint or not secret:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "connection needs 'endpoint' and 'secret'",
                                 details={"missing": [k for k in ("endpoint", "secret") if not connection.get(k)]})
        return endpoint.rstrip("/"), secret

    def _call(self, method: str, url: str, secret: str, body: bytes = b"", extra_headers: dict | None = None) -> httpx.Response:
        headers = {"Content-Type": "application/json", "X-IncuBrix-Signature": sign(secret, body), **(extra_headers or {})}
        try:
            with httpx.Client(timeout=self.settings.http_timeout_s, transport=self.transport) as client:
                resp = client.request(method, url, content=body, headers=headers)
        except httpx.TimeoutException:
            raise ConnectorError(ErrorCode.PLATFORM_UNAVAILABLE, "partner timed out", details={"reason": "timeout"})
        except httpx.HTTPError as exc:
            raise ConnectorError(ErrorCode.PLATFORM_UNAVAILABLE, "partner unreachable", details={"reason": type(exc).__name__})
        if resp.status_code >= 400:
            raise self.error_from_response(resp)
        return resp

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        endpoint, secret = self._endpoint_and_secret(connection)
        body = json.dumps({"idempotency_key": idempotency_key, "destination_id": destination.id,
                           "title": rendition.title, "body": rendition.body, "canonical_url": rendition.canonical_url,
                           "tags": rendition.tags, "ai_generated": rendition.ai_generated},
                          sort_keys=True).encode()
        headers = {"Idempotency-Key": idempotency_key}  # lets the partner dedupe on its side too
        if self.settings.simulation_mode and destination.config.get("simulate"):
            headers["X-Simulate"] = str(destination.config["simulate"])
        data = self._call("POST", endpoint, secret, body, headers).json()
        return {"platform_post_id": str(data["id"]), "live_url": data.get("url"), "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        endpoint, secret = self._endpoint_and_secret(connection)
        data = self._call("GET", f"{endpoint}/{platform_post_id}", secret).json()
        return {"status": data.get("status", "unknown"), "live_url": data.get("url")}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        endpoint, secret = self._endpoint_and_secret(connection)
        self._call("DELETE", f"{endpoint}/{platform_post_id}", secret)
        return {"deleted": True}
