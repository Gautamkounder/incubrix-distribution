"""Dev.to (Forem): publish an article, read its status, remove it. Dev.to has no delete endpoint, so delete = unpublish."""
import re

from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

DEFAULT_ENDPOINT = "https://dev.to"


def clean_tags(tags: list[str]) -> list[str]:
    """Dev.to tags: letters and digits only, at most 4."""
    out: list[str] = []
    for t in tags:
        t = re.sub(r"[^a-z0-9]", "", t.lower())
        if t and t not in out:
            out.append(t)
    return out[:4]


class DevtoConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        key = connection.get("api_key")
        if not key:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "connection needs 'api_key'",
                                 details={"missing": ["api_key"]})
        headers = {"api-key": key, "Accept": "application/vnd.forem.api-v1+json"}
        return (connection.get("endpoint") or DEFAULT_ENDPOINT).rstrip("/"), headers

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        article: dict = {"title": rendition.title, "body_markdown": rendition.body,
                         "published": True, "tags": clean_tags(rendition.tags)}
        if rendition.canonical_url:
            article["canonical_url"] = rendition.canonical_url
        data = call(self, "POST", f"{base}/api/articles", headers, {"article": article}).json()
        return {"platform_post_id": str(data["id"]), "live_url": data.get("url"), "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        data = call(self, "GET", f"{base}/api/articles/{platform_post_id}", headers).json()
        return {"status": "live" if data.get("published", True) else "removed", "live_url": data.get("url")}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        call(self, "PUT", f"{base}/api/articles/{platform_post_id}", headers, {"article": {"published": False}})
        return {"deleted": True, "method": "unpublished"}
    