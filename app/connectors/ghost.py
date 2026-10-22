"""Ghost connector: Admin API for posting, fetching status, and deleting posts."""
from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

class GhostConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        endpoint = connection.get("endpoint")
        admin_key = connection.get("admin_api_key")
        if not endpoint or not admin_key:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "Ghost connection requires 'endpoint' and 'admin_api_key'")
        headers = {"Authorization": f"Ghost {admin_key}"}
        return endpoint.rstrip("/"), headers

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        post_data = {
            "posts": [{
                "title": rendition.title,
                "html": f"<p>{rendition.body}</p>",
                "status": "published",
                "tags": rendition.tags
            }]
        }
        res = call(self, "POST", f"{base}/ghost/api/admin/posts/", headers, post_data).json()
        post = res["posts"][0]
        return {"platform_post_id": str(post["id"]), "live_url": post.get("url"), "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        res = call(self, "GET", f"{base}/ghost/api/admin/posts/{platform_post_id}/", headers).json()
        post = res["posts"][0]
        return {"status": "live" if post.get("status") == "published" else "removed", "live_url": post.get("url")}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        call(self, "DELETE", f"{base}/ghost/api/admin/posts/{platform_post_id}/", headers)
        return {"deleted": True}
