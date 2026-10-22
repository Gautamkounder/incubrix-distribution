from datetime import datetime, timedelta, timezone

from app.db import Publication, session_scope
from app.rules import DISCLOSURE_LINE, evaluate
from app.schemas import Destination, Rendition
from tests.conftest import publish

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def dest(rules=None, dest_id="d1"):
    return Destination(id=dest_id, connector_key="webhook", config={"rules": rules or {}})


def rend(**kw):
    return Rendition(title="T", body="Body", **kw)


# ---------- pure engine ----------
def test_no_rules_allows():
    assert evaluate(rend(), dest(), [], NOW).action == "allow"


def test_second_post_inside_weekly_cap_is_rescheduled_to_when_slot_opens():
    d = dest({"frequency_cap": {"max_posts": 1, "window_hours": 168}})
    first = NOW - timedelta(days=2)
    decision = evaluate(rend(), d, [first], NOW)
    assert decision.action == "reschedule"
    assert decision.reschedule_at == first + timedelta(days=7)
    assert decision.violation.code.value == "DEST_RULE_FREQUENCY_CAP"


def test_post_outside_window_is_allowed():
    d = dest({"frequency_cap": {"max_posts": 1, "window_hours": 168}})
    assert evaluate(rend(), d, [NOW - timedelta(days=8)], NOW).action == "allow"


def test_cap_of_two_allows_one_more_then_blocks_with_correct_slot():
    d = dest({"frequency_cap": {"max_posts": 2, "window_hours": 24}})
    a, b = NOW - timedelta(hours=10), NOW - timedelta(hours=3)
    assert evaluate(rend(), d, [a], NOW).action == "allow"
    decision = evaluate(rend(), d, [a, b], NOW)
    assert decision.action == "reschedule" and decision.reschedule_at == a + timedelta(hours=24)


def test_promotional_post_to_no_promo_destination_is_blocked():
    d = evaluate(rend(is_promotional=True), dest({"self_promo_allowed": False}), [], NOW)
    assert d.action == "block" and d.violation.code.value == "DEST_RULE_SELF_PROMOTION"


def test_non_promotional_post_to_no_promo_destination_is_allowed():
    assert evaluate(rend(), dest({"self_promo_allowed": False}), [], NOW).action == "allow"


def test_link_policy_none_blocks_any_link():
    d = evaluate(Rendition(title="T", body="see https://a.com"), dest({"link_policy": {"allowed": False}}), [], NOW)
    assert d.action == "block" and d.violation.code.value == "DEST_RULE_LINK_POLICY"


def test_canonical_url_counts_as_a_link():
    r = Rendition(title="T", body="no links here", canonical_url="https://a.com/x")
    assert evaluate(r, dest({"link_policy": {"allowed": False}}), [], NOW).action == "block"


def test_max_links_limit():
    r = Rendition(title="T", body="https://a.com https://b.com https://c.com")
    d = evaluate(r, dest({"link_policy": {"max_links": 2}}), [], NOW)
    assert d.action == "block" and d.violation.details["actual"] == 3


def test_ai_disclosure_is_appended_once():
    d = dest({"disclosure_required": True})
    decision = evaluate(rend(ai_generated=True), d, [], NOW)
    assert decision.rendition.body.endswith(DISCLOSURE_LINE) and decision.notes
    again = evaluate(decision.rendition.model_copy(update={"ai_generated": True}), d, [], NOW)
    assert again.rendition.body.count(DISCLOSURE_LINE) == 1 and not again.notes


def test_disclosure_not_added_to_human_written_content():
    decision = evaluate(rend(ai_generated=False), dest({"disclosure_required": True}), [], NOW)
    assert DISCLOSURE_LINE not in decision.rendition.body


# ---------- through the API ----------
def payload(dest_id="forum", rules=None, **rendition_extra):
    return {"rendition": {"title": "T", "body": "Body", **rendition_extra},
            "targets": [{"destination": {"id": dest_id, "connector_key": "webhook", "config": {"rules": rules or {}}},
                         "connection": {"endpoint": "https://p.example/h", "secret": "s"}}]}


def result(client, job_id):
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded", job
    return job["result"]["destinations"][0]


def count():
    with session_scope() as db:
        return db.query(Publication).count()


WEEKLY = {"frequency_cap": {"max_posts": 1, "window_hours": 168}}


def test_api_second_post_inside_weekly_cap_is_rescheduled_not_posted(client):
    first = result(client, publish(client, payload(rules=WEEKLY), key="a").json()["job_id"])
    second = result(client, publish(client, payload(rules=WEEKLY), key="b").json()["job_id"])
    assert first["status"] == "published"
    assert second["status"] == "rescheduled"
    assert second["error"]["code"] == "DEST_RULE_FREQUENCY_CAP" and second["error"]["retryable"] is True
    assert second["reschedule_at"] and count() == 1  # the second post was never sent


def test_api_cap_is_per_destination(client):
    result(client, publish(client, payload("forum-a", WEEKLY), key="a").json()["job_id"])
    other = result(client, publish(client, payload("forum-b", WEEKLY), key="b").json()["job_id"])
    assert other["status"] == "published"


def test_api_old_post_outside_window_does_not_block(client):
    with session_scope() as db:
        db.add(Publication(job_id="old", destination_id="forum", connector_key="webhook", idempotency_key="old:forum",
                           platform_post_id="p0", created_at=datetime.now(timezone.utc) - timedelta(days=8)))
    assert result(client, publish(client, payload(rules=WEEKLY), key="a").json()["job_id"])["status"] == "published"


def test_api_retry_with_same_key_is_not_blocked_by_its_own_cap(client):
    a = publish(client, payload(rules=WEEKLY), key="same").json()["job_id"]
    result(client, a)
    again = publish(client, payload(rules=WEEKLY), key="same")
    assert again.json()["job_id"] == a and count() == 1


def test_api_promo_post_to_no_promo_destination_blocked_and_not_sent(client):
    d = result(client, publish(client, payload(rules={"self_promo_allowed": False}, is_promotional=True)).json()["job_id"])
    assert d["status"] == "blocked" and d["error"]["code"] == "DEST_RULE_SELF_PROMOTION"
    assert d["error"]["details"]["rule"] == "self_promotion" and count() == 0


def test_api_ai_disclosure_added_and_reported_in_warnings(client):
    job_id = publish(client, payload(rules={"disclosure_required": True}, ai_generated=True)).json()["job_id"]
    d = result(client, job_id)
    assert d["status"] == "published" and any("ai_disclosure" in w for w in d["warnings"])
    manifest = client.get(f"/api/v1/jobs/{job_id}").json()["result"]["manifest"]
    assert any("ai_disclosure" in w for w in manifest["warnings"])


def test_api_bad_rules_config_gives_clear_error(client):
    d = result(client, publish(client, payload(rules={"frequency_cap": {"max_posts": 1}})).json()["job_id"])
    assert d["status"] == "failed" and d["error"]["code"] == "VALIDATION_ERROR"
