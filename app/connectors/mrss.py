from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

class MRSSConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        endpoint = connection.get("endpoint")
        api_key = connection.get("api_key")
        if not endpoint or not api_key:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "MRSS requires 'endpoint' and 'api_key'")
        return endpoint.rstrip("/"), {"x-api-key": api_key, "Content-Type": "application/json"}

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        payload = {"title": rendition.title, "description": rendition.body, "idempotency_key": idempotency_key}
        res = call(self, "POST", f"{base}/feed/items", headers, payload).json()
        return {"platform_post_id": str(res["item_id"]), "live_url": res.get("url"), "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        res = call(self, "GET", f"{base}/feed/items/{platform_post_id}", headers).json()
        return {"status": "live" if res.get("active") else "removed", "live_url": res.get("url")}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        call(self, "DELETE", f"{base}/feed/items/{platform_post_id}", headers)
        return {"deleted": True}
