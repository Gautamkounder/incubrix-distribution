import httpx
import pytest

from app.connectors.base import load_manifest
from app.connectors.registry import get_registry
from app.security import sign, verify

BODY = {"rendition": {"title": "T", "body": "B"},
        "destination": {"id": "d1", "connector_key": "webhook"},
        "connection": {"endpoint": "https://partner.example/h", "secret": "s3cret"},
        "idempotency_key": "idem-1"}


def test_contract_publish_status_delete_roundtrip(client):
    pub = client.post("/connector/v1/webhook/publish", json=BODY)
    assert pub.status_code == 200
    post_id = pub.json()["platform_post_id"]
    st = client.post("/connector/v1/webhook/get_status", json={"platform_post_id": post_id, "connection": BODY["connection"]})
    assert st.json()["status"] == "live"
    de = client.post("/connector/v1/webhook/delete", json={"platform_post_id": post_id, "connection": BODY["connection"]})
    assert de.json() == {"deleted": True}


def test_contract_same_idempotency_key_same_post_id(client):
    a = client.post("/connector/v1/webhook/publish", json=BODY).json()["platform_post_id"]
    b = client.post("/connector/v1/webhook/publish", json=BODY).json()["platform_post_id"]
    assert a == b


def test_contract_validate(client):
    body = {**BODY, "rendition": {"title": "x" * 400, "body": "B"}}
    r = client.post("/connector/v1/webhook/validate", json=body).json()
    assert r["ok"] is False and r["violations"][0]["field"] == "title"


def test_contract_unsupported_method_is_501_with_shared_shape(client):
    r = client.post("/connector/v1/webhook/fetch_metrics", json={"platform_post_id": "x", "connection": {}})
    assert r.status_code == 501 and r.json()["error"]["code"] == "METHOD_NOT_SUPPORTED"


def test_contract_platform_error_uses_shared_code_and_status(client):
    body = {**BODY, "destination": {"id": "d1", "connector_key": "webhook", "config": {"simulate": "429"}}}
    r = client.post("/connector/v1/webhook/publish", json=body)
    assert r.status_code == 429 and r.json()["error"]["code"] == "PLATFORM_RATE_LIMIT"
    assert r.json()["error"]["retryable"] is True


def test_missing_connection_fields(client):
    body = {**BODY, "connection": {}}
    r = client.post("/connector/v1/webhook/publish", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONNECTION_INVALID"


def test_assisted_pack_via_contract(client):
    r = client.post("/connector/v1/assisted/build_assist_pack",
                    json={"rendition": {"title": "T", "body": "B"}, "destination": {"id": "g", "connector_key": "assisted"}})
    assert r.status_code == 200 and r.json()["checklist"]


def test_every_manifest_loads_and_uses_only_shared_error_codes(client):
    for connector in get_registry().connectors.values():
        m = load_manifest(__import__("pathlib").Path(f"app/connectors/manifests/{connector.key}.yaml"))
        assert m.key == connector.key and m.surfaces


def test_hmac_signature_roundtrip():
    sig = sign("k", b"payload")
    assert sig.startswith("sha256=") and verify("k", b"payload", sig)
    assert not verify("k", b"tampered", sig) and not verify("other", b"payload", sig)


def test_signature_header_is_sent_to_partner(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.connectors.webhook import WebhookConnector
    from app.schemas import Destination, Rendition
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["sig"], seen["body"] = request.headers["X-IncuBrix-Signature"], request.content
        return httpx.Response(201, json={"id": "p1", "url": "https://x/p1"})

    get_settings.cache_clear()
    connector = WebhookConnector(load_manifest(__import__("pathlib").Path("app/connectors/manifests/webhook.yaml")),
                                 get_settings(), httpx.MockTransport(handler))
    connector.publish(Rendition(title="t", body="b"), Destination(id="d", connector_key="webhook"),
                      {"endpoint": "https://x/hook", "secret": "abc"}, "idem")
    assert verify("abc", seen["body"], seen["sig"])
