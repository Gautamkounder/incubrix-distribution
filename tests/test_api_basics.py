from tests.conftest import publish, webhook_request


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready").json()
    assert ready["status"] == "ready" and "webhook" in ready["connectors"]
    assert client.get("/api/v1/health").status_code == 200


def test_correlation_id_is_echoed(client):
    r = client.get("/health", headers={"X-Correlation-Id": "abc-123"})
    assert r.headers["X-Correlation-Id"] == "abc-123"


def test_error_shape_for_missing_idempotency_key(client):
    r = client.post("/api/v1/publish", json=webhook_request())
    assert r.status_code == 400
    err = r.json()["error"]
    assert set(err) == {"code", "message", "retryable", "details"}
    assert err["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_validation_error_uses_same_shape(client):
    r = client.post("/api/v1/publish", json={"rendition": {}}, headers={"Idempotency-Key": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_connector_rejected_before_job_created(client):
    payload = webhook_request()
    payload["targets"][0]["destination"]["connector_key"] = "nope"
    r = publish(client, payload)
    assert r.status_code == 404 and r.json()["error"]["code"] == "UNKNOWN_CONNECTOR"


def test_unknown_job_is_404(client):
    r = client.get("/api/v1/jobs/doesnotexist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_list_connectors(client):
    keys = {c["key"] for c in client.get("/api/v1/connectors").json()}
    assert {"webhook", "assisted"} <= keys
