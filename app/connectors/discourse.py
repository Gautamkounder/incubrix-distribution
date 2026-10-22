"""Discourse: create a topic, read its status, delete it. Needs an API key and the user it posts as."""
from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition


class DiscourseConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        endpoint, key, user = connection.get("endpoint"), connection.get("api_key"), connection.get("api_username")
        missing = [k for k, v in (("endpoint", endpoint), ("api_key", key), ("api_username", user)) if not v]
        if missing:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID,
                                 "connection needs 'endpoint', 'api_key' and 'api_username'",
                                 details={"missing": missing})
        return endpoint.rstrip("/"), {"Api-Key": key, "Api-Username": user}

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        payload: dict = {"title": rendition.title, "raw": rendition.body, "tags": rendition.tags}
        if destination.config.get("category_id") is not None:
            payload["category"] = int(destination.config["category_id"])
        data = call(self, "POST", f"{base}/posts.json", headers, payload).json()
        if "topic_id" not in data:  # e.g. the post went to the moderator approval queue
            raise ConnectorError(ErrorCode.PLATFORM_CONTENT_REJECTED,
                                 "Discourse did not create the topic (it may be waiting for moderator approval)",
                                 details={"platform_response": str(data)[:300]})
        topic_id = data["topic_id"]
        slug = data.get("topic_slug") or "topic"
        return {"platform_post_id": str(topic_id), "live_url": f"{base}/t/{slug}/{topic_id}", "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        data = call(self, "GET", f"{base}/t/{platform_post_id}.json", headers).json()
        slug = data.get("slug") or "topic"
        return {"status": "deleted" if data.get("deleted_at") else "live",
                "live_url": f"{base}/t/{slug}/{platform_post_id}"}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        call(self, "DELETE", f"{base}/t/{platform_post_id}.json", headers)
        return {"deleted": True}