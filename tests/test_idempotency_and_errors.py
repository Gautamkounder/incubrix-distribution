import json

import pytest

from app.db import Publication, session_scope
from tests.conftest import publish, webhook_request


def _count_publications():
    with session_scope() as db:
        return db.query(Publication).count()


def test_same_key_same_request_returns_same_job_and_one_post(client):
    p = webhook_request()
    a = publish(client, p, key="same")
    b = publish(client, p, key="same")
    assert a.status_code == b.status_code == 202
    assert a.json()["job_id"] == b.json()["job_id"]
    assert b.headers["Idempotent-Replay"] == "true"
    assert _count_publications() == 1  # never a second post


def test_same_key_different_request_is_409(client):
    publish(client, webhook_request(title="one"), key="dup")
    r = publish(client, webhook_request(title="two"), key="dup")
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_different_keys_make_different_posts(client):
    a = publish(client, webhook_request(), key="a").json()["job_id"]
    b = publish(client, webhook_request(), key="b").json()["job_id"]
    assert a != b and _count_publications() == 2


@pytest.mark.parametrize("sim,code,retryable", [
    ("429", "PLATFORM_RATE_LIMIT", True),
    ("401", "CONNECTION_AUTH_EXPIRED", False),
    ("422", "PLATFORM_CONTENT_REJECTED", False),
    ("503", "PLATFORM_UNAVAILABLE", True),
    ("timeout", "PLATFORM_UNAVAILABLE", True),
])
def test_platform_errors_map_to_shared_codes(client, sim, code, retryable):
    job_id = publish(client, webhook_request(simulate=sim)).json()["job_id"]
    d = client.get(f"/api/v1/jobs/{job_id}").json()["result"]["destinations"][0]
    assert d["status"] == "failed"
    assert d["error"]["code"] == code and d["error"]["retryable"] is retryable


def test_429_reports_platform_reset_time(client):
    job_id = publish(client, webhook_request(simulate="429")).json()["job_id"]
    d = client.get(f"/api/v1/jobs/{job_id}").json()["result"]["destinations"][0]
    assert d["error"]["details"]["retry_after_s"] == 30


def test_failed_post_creates_no_publication(client):
    publish(client, webhook_request(simulate="timeout"))
    assert _count_publications() == 0


def test_secret_never_stored_in_database_or_job_response(client):
    job_id = publish(client, webhook_request()).json()["job_id"]
    body = json.dumps(client.get(f"/api/v1/jobs/{job_id}").json())
    assert "super-secret-value" not in body
    from app.db import Job
    with session_scope() as db:
        stored = json.dumps(db.get(Job, job_id).request)
    assert "super-secret-value" not in stored and "***" in stored
