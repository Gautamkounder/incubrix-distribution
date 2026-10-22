"""Shared HTTP call for connectors that talk to a platform API. Maps failures to the shared error codes."""
import httpx

from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode


def call(connector: Connector, method: str, url: str, headers: dict, json_body: dict | None = None) -> httpx.Response:
    try:
        with httpx.Client(timeout=connector.settings.http_timeout_s, transport=connector.transport) as client:
            resp = client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException:
        raise ConnectorError(ErrorCode.PLATFORM_UNAVAILABLE, "platform timed out", details={"reason": "timeout"})
    except httpx.HTTPError as exc:
        raise ConnectorError(ErrorCode.PLATFORM_UNAVAILABLE, "platform unreachable",
                             details={"reason": type(exc).__name__})
    if resp.status_code >= 400:
        raise connector.error_from_response(resp)
    return resp