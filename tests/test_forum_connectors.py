import json
from pathlib import Path

import httpx
import pytest

from app.certification import certify
from app.config import get_settings
from app.connectors.base import load_manifest
from app.connectors.devto import DevtoConnector
from app.connectors.discourse import DiscourseConnector
from app.connectors.mock_forums import make_forum_transport
from app.connectors.registry import get_registry
from app.errors import AppError, ErrorCode
from app.schemas import Destination, Rendition
from app.rules import evaluate  # noqa: F401  (keeps import order stable with the other test files)
from tests.conftest import publish

MANIFESTS = Path(__file__).resolve().parent.parent / "app" / "connectors" / "manifests"
D_DEST = Destination(id="disc", connector_key="discourse", config={"category_id": 4})
D_CONN = {"endpoint": "https://forum.example", "api_key": "disc-secret", "api_username": "system"}
V_DEST = Destination(id="dev", connector_key="devto")
V_CONN = {"api_key": "dev-secret"}


def make(cls, name, transport=None):
    return cls(load_manifest(MANIFESTS / f"{name}.yaml"), get_settings(), transport=transport or make_forum_transport())


def recording():
    inner, seen = make_forum_transport(), []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return inner.handle_request(request)

    return httpx.MockTransport(handler), seen


def steps_of(result):
    return {s["step"]: s["ok"] for s in result["steps"]}


def test_discourse_passes_certification():
    result = certify(make(DiscourseConnector, "discourse"), D_DEST, D_CONN)
    assert result["certified"] is True, result["steps"]
    assert set(steps_of(result)) == {"validate", "publish", "confirm_live", "delete", "confirm_gone"}


def test_devto_passes_certification():
    result = certify(make(DevtoConnector, "devto"), V_DEST, V_CONN)
    assert result["certified"] is True, result["steps"]


def test_discourse_sends_auth_headers_and_category():
    transport, seen = recording()
    c = make(DiscourseConnector, "discourse", transport)
    res = c.publish(Rendition(title="Hello forum", body="Body text", tags=["a"]), D_DEST, D_CONN, "k1")
    req = seen[0]
    assert req.headers["api-key"] == "disc-secret" and req.headers["api-username"] == "system"
    payload = json.loads(req.content)
    assert payload["category"] == 4 and payload["title"] == "Hello forum" and payload["raw"] == "Body text"
    assert res["live_url"].startswith("https://forum.example/t/hello-forum/")


def test_discourse_missing_credentials():
    c = make(DiscourseConnector, "discourse")
    with pytest.raises(AppError) as e:
        c.publish(Rendition(title="T", body="B"), D_DEST, {"endpoint": "https://forum.example"}, "k")
    assert e.value.code == ErrorCode.CONNECTION_INVALID
    assert e.value.details["missing"] == ["api_key", "api_username"]


def test_discourse_rate_limit_keeps_retry_after():
    transport = httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "30"}, json={}))
    c = make(DiscourseConnector, "discourse", transport)
    with pytest.raises(AppError) as e:
        c.publish(Rendition(title="T", body="B"), D_DEST, D_CONN, "k")
    assert e.value.code == ErrorCode.PLATFORM_RATE_LIMIT and e.value.retryable is True
    assert e.value.details["retry_after_s"] == 30


def test_devto_tags_are_cleaned_and_limited_to_four():
    transport, seen = recording()
    c = make(DevtoConnector, "devto", transport)
    c.publish(Rendition(title="T", body="B", tags=["Machine Learning!", "Python", "python", "a", "b", "c"]),
              V_DEST, V_CONN, "k")
    assert json.loads(seen[0].content)["article"]["tags"] == ["machinelearning", "python", "a", "b"]


def test_devto_delete_unpublishes_and_post_is_then_gone():
    c = make(DevtoConnector, "devto")
    post_id = c.publish(Rendition(title="T", body="B"), V_DEST, V_CONN, "k")["platform_post_id"]
    assert c.delete(post_id, V_CONN)["method"] == "unpublished"
    with pytest.raises(AppError) as e:
        c.get_status(post_id, V_CONN)
    assert e.value.details["platform_status"] == 404


def test_registry_has_the_new_connectors():
    assert {"discourse", "devto"} <= set(get_registry().connectors)


def test_api_publish_to_discourse_and_devto(client):
    cases = [("discourse", D_CONN, "a"), ("devto", V_CONN, "b")]
    for name, conn, key in cases:
        payload = {"rendition": {"title": "Hello forum", "body": "Body"},
                   "targets": [{"destination": {"id": f"{name}-1", "connector_key": name, "config": {}},
                                "connection": conn}]}
        job_id = publish(client, payload, key=key).json()["job_id"]
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        d = job["result"]["destinations"][0]
        assert job["status"] == "succeeded" and d["status"] == "published", d
        assert d["platform_post_id"]