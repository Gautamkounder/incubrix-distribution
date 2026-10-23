from app.connectors._http import call
from app.connectors.base import Connector
from app.errors import ConnectorError, ErrorCode
from app.schemas import Destination, Rendition

class SlackConnector(Connector):
    def _conn(self, connection: dict) -> tuple[str, dict]:
        endpoint = connection.get("endpoint", "https://slack.com/api")
        token = connection.get("bot_token")
        if not token:
            raise ConnectorError(ErrorCode.CONNECTION_INVALID, "Slack requires 'bot_token'")
        return endpoint.rstrip("/"), {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def publish(self, rendition: Rendition, destination: Destination, connection: dict, idempotency_key: str) -> dict:
        base, headers = self._conn(connection)
        channel = destination.config.get("channel_id")
        payload = {"channel": channel, "text": f"*{rendition.title}*\n{rendition.body}"}
        res = call(self, "POST", f"{base}/chat.postMessage", headers, payload).json()
        if not res.get("ok"):
            raise ConnectorError(ErrorCode.PLATFORM_CONTENT_REJECTED, res.get("error", "Slack error"))
        return {"platform_post_id": res["ts"], "live_url": f"slack://channel?id={channel}&message={res['ts']}", "status": "live"}

    def get_status(self, platform_post_id: str, connection: dict) -> dict:
        return {"status": "live", "live_url": ""}

    def delete(self, platform_post_id: str, connection: dict) -> dict:
        base, headers = self._conn(connection)
        channel = destination.config.get("channel_id")
        call(self, "POST", f"{base}/chat.delete", headers, {"channel": channel, "ts": platform_post_id})
        return {"deleted": True}
