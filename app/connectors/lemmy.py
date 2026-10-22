"""Lemmy connector: ActivityPub community network for publishing posts."""
from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

class LemmyConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        endpoint = connection.get("endpoint")
        jwt = connection.get("auth_jwt")
        if not endpoint or not jwt:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "Lemmy connection requires 'endpoint' and 'auth_jwt'")
        headers = {"Authorization": f"Bearer {jwt}"}
        return endpoint.rstrip("/"), headers

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        community_id = destination.config.get("community_id", 1)
        payload = {
            "auth": connection.get("auth_jwt"),
            "community_id": int(community_id),
            "name": rendition.title,
            "body": rendition.body,
        }
        if rendition.canonical_url:
            payload["url"] = rendition.canonical_url
        res = call(self, "POST", f"{base}/api/v3/post", headers, payload).json()
        post_view = res.get("post_view", {})
        post = post_view.get("post", res)
        post_id = str(post["id"])
        return {"platform_post_id": post_id, "live_url": f"{base}/post/{post_id}", "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        res = call(self, "GET", f"{base}/api/v3/post?id={platform_post_id}", headers).json()
        post_view = res.get("post_view", {})
        post = post_view.get("post", {})
        if post.get("deleted") or post.get("removed"):
            return {"status": "deleted", "live_url": f"{base}/post/{platform_post_id}"}
        return {"status": "live", "live_url": f"{base}/post/{platform_post_id}"}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        payload = {"auth": connection.get("auth_jwt"), "post_id": int(platform_post_id), "deleted": True}
        call(self, "POST", f"{base}/api/v3/post/delete", headers, payload)
        return {"deleted": True}
