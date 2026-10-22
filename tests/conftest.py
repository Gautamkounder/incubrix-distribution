import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SIMULATION_MODE", "true")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    get_settings.cache_clear()
    from app.main import app
    with TestClient(app) as c:  # the 'with' runs startup (creates tables)
        yield c
    get_settings.cache_clear()


def webhook_request(dest_id="partner-1", simulate=None, title="Hello", spec=None):
    config = {}
    if simulate:
        config["simulate"] = simulate
    if spec:
        config["spec"] = spec
    return {
        "rendition": {"title": title, "body": "Body text https://example.com"},
        "targets": [{"destination": {"id": dest_id, "connector_key": "webhook", "config": config},
                     "connection": {"endpoint": "https://partner.example/hooks", "secret": "super-secret-value"}}],
    }


def publish(client, payload, key="k1"):
    return client.post("/api/v1/publish", json=payload, headers={"Idempotency-Key": key})
