from tests.conftest import publish, webhook_request


def _finished(client, job_id):
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded", job
    assert job["progress"] == 100
    return job


def test_publish_returns_202_and_job_completes(client):
    r = publish(client, webhook_request())
    assert r.status_code == 202
    job = _finished(client, r.json()["job_id"])
    dest = job["result"]["destinations"][0]
    assert dest["status"] == "published" and dest["live_url"].startswith("https://partner.example/posts/")
    assert job["links"]["manifest"]


def test_manifest_has_required_fields(client):
    job = _finished(client, publish(client, webhook_request()).json()["job_id"])
    m = job["result"]["manifest"]
    for field in ("connectors", "models", "settings", "seed", "timings_ms", "cost_estimate_usd", "warnings", "rights"):
        assert field in m


def test_assisted_connector_builds_pack(client):
    payload = {"rendition": {"title": "Hi", "body": "Body", "ai_generated": True},
               "targets": [{"destination": {"id": "g1", "connector_key": "assisted",
                            "config": {"rules_url": "https://x/rules", "submit_url": "https://x/submit", "rules": {"self_promo_allowed": False}}}}]}
    job = _finished(client, publish(client, payload).json()["job_id"])
    d = job["result"]["destinations"][0]
    assert d["status"] == "assist_pack"
    assert d["assist_pack"]["deep_link"] == "https://x/submit"
    assert any("Disclose" in c for c in d["assist_pack"]["checklist"])
    assert any("NOT allowed" in c for c in d["assist_pack"]["checklist"])
    assert {f["name"] for f in d["assist_pack"]["files"]} >= {"caption.txt", "post.md"}


def test_spec_violation_is_blocked_with_field_reasons(client):
    job = _finished(client, publish(client, webhook_request(title="x" * 50, spec={"title_max_chars": 20})).json()["job_id"])
    d = job["result"]["destinations"][0]
    assert d["status"] == "blocked" and d["error"]["code"] == "DEST_SPEC_VIOLATION"
    assert d["error"]["details"]["violations"][0] == {"field": "title", "reason": "too_long", "limit": 20, "actual": 50}


def test_config_not_code_new_destination_is_just_data(client):
    # "adding forum number 41 is one catalogue row": a new destination needs no new code
    for n in range(3):
        job = _finished(client, publish(client, webhook_request(dest_id=f"site-{n}"), key=f"k{n}").json()["job_id"])
        assert job["result"]["destinations"][0]["status"] == "published"


def test_multiple_targets_one_failure_does_not_stop_others(client):
    payload = webhook_request(dest_id="ok-site")
    bad = webhook_request(dest_id="bad-site", simulate="422")["targets"][0]
    payload["targets"].append(bad)
    job = _finished(client, publish(client, payload).json()["job_id"])
    statuses = {d["destination_id"]: d["status"] for d in job["result"]["destinations"]}
    assert statuses == {"ok-site": "published", "bad-site": "failed"}
    assert job["result"]["manifest"]["warnings"] == ["bad-site: PLATFORM_CONTENT_REJECTED"]
