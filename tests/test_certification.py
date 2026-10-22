import json
from pathlib import Path

import httpx

from app.certification import certify
from app.config import get_settings
from app.connectors.base import load_manifest
from app.connectors.webhook import WebhookConnector
from app.schemas import Destination

MANIFEST = Path(__file__).resolve().parent.parent / "app" / "connectors" / "manifests" / "webhook.yaml"
DEST = Destination(id="cert-dest", connector_key="webhook")
CONN = {"endpoint": "https://partner.example/posts", "secret": "super-secret-value"}


def make_connector(delete_works=True, publish_status=201):
    posts: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            if publish_status >= 400:
                return httpx.Response(publish_status, json={"error": "nope"})
            posts["p1"] = True
            return httpx.Response(201, json={"id": "p1", "url": "https://partner.example/p1"})
        post_id = path.rsplit("/", 1)[-1]
        if request.method == "GET":
            if post_id in posts:
                return httpx.Response(200, json={"status": "live", "url": "https://partner.example/p1"})
            return httpx.Response(404, json={"error": "not found"})
        if request.method == "DELETE":
            if delete_works:
                posts.pop(post_id, None)
            return httpx.Response(200, json={})
        return httpx.Response(405)

    return WebhookConnector(load_manifest(MANIFEST), get_settings(), transport=httpx.MockTransport(handler))


def steps_of(result):
    return {s["step"]: s["ok"] for s in result["steps"]}


def test_full_lifecycle_certifies():
    result = certify(make_connector(), DEST, CONN)
    assert result["certified"] is True
    assert steps_of(result) == {"validate": True, "publish": True, "confirm_live": True,
                                "delete": True, "confirm_gone": True}
    assert result["post_id"] == "p1"


def test_delete_that_does_not_really_delete_fails_certification():
    result = certify(make_connector(delete_works=False), DEST, CONN)
    assert result["certified"] is False
    assert steps_of(result)["confirm_gone"] is False


def test_publish_failure_fails_and_never_tries_delete():
    result = certify(make_connector(publish_status=422), DEST, CONN)
    assert result["certified"] is False
    assert steps_of(result) == {"validate": True, "publish": False}


def test_evidence_file_is_written_without_secrets(tmp_path):
    result = certify(make_connector(), DEST, CONN, evidence_dir=tmp_path)
    text = Path(result["evidence_file"]).read_text(encoding="utf-8")
    assert "super-secret-value" not in text
    assert json.loads(text)["certified"] is True
    assert json.loads(text)["connection"]["secret"] == "***"