from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

class HashnodeConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        endpoint = connection.get("endpoint", "https://api.hashnode.com/v1")
        token = connection.get("auth_token")
        if not token:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "Hashnode requires 'auth_token'")
        return endpoint.rstrip("/"), {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        payload = {"title": rendition.title, "contentMarkdown": rendition.body, "tags": rendition.tags}
        res = call(self, "POST", f"{base}/publish", headers, payload).json()
        return {"platform_post_id": str(res["post_id"]), "live_url": res.get("url"), "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        res = call(self, "GET", f"{base}/posts/{platform_post_id}", headers).json()
        return {"status": "live" if res.get("published") else "removed", "live_url": res.get("url")}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        call(self, "DELETE", f"{base}/posts/{platform_post_id}", headers)
        return {"deleted": True}
