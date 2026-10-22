# IncuBrix Long-Tail Distribution: connector service

Publishes one piece of content to many small destinations (forums, blogs, partner sites), following the IncuBrix
connector contract. One connector serves many destinations; a destination is data, not code.

**Status: Day 2 in progress.** Working: API, jobs, idempotency, error codes, logging, storage, manifests, webhook (HMAC)
and assisted connectors, posting-rules engine, batch runner, 59 tests. Not built yet: certification harness, Discourse /
Lemmy / Dev.to / Ghost connectors, local Ghost + Lemmy in compose, catalogue tools (see REPORT.md when written).

## Run it (Windows PowerShell or any shell)
```
copy .env.example .env
docker compose up --build            # api + postgres  -> http://localhost:8000/docs
# optional S3-compatible storage (RustFS): set STORAGE_BACKEND=s3 in .env, then
# docker compose --profile s3 up --build
```
Without Docker:
```
python -m venv .venv
.venv\Scripts\Activate.ps1           # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tests (no API keys needed)
```
pytest
```

## Batch runner
```
python -m tools.batch_runner --input samples --out batch_out --api-url http://localhost:8000
```
Runs every `.json` in the folder against the API and writes one `*.result.json` per input plus `summary.json`.

## API (all under /api/v1/)
| Route | Purpose |
|---|---|
| `POST /api/v1/publish` | Needs an `Idempotency-Key` header. Returns `202` + `job_id`. |
| `GET /api/v1/jobs/{job_id}` | `status` (queued, running, succeeded, failed), `progress` 0-100, results, manifest link |
| `GET /api/v1/connectors` | Loaded connector manifests |
| `POST /connector/v1/{connector_key}/{method}` | Connector contract (Appendix A): validate, publish, get_status, delete, fetch_metrics, refresh_auth, build_assist_pack |
| `GET /health`, `GET /ready` | Also available under `/api/v1/` |

`openapi.yaml` is generated from the running app (`python -m tools.export_openapi`); a test fails if it drifts.

## Settings
Every setting is an environment variable. See `.env.example` (nothing is hard-coded). `SIMULATION_MODE=true` uses mock
platforms, so everything runs with no real accounts. In simulation, `destination.config.simulate` can be
`timeout`, `429`, `401`, `422` or `503` to force that failure.

## Error codes
Every error is `{"error": {"code", "message", "retryable", "details"}}`.

| Code | Retryable | Meaning |
|---|---|---|
| DEST_SPEC_VIOLATION | no | Content breaks the destination's format limits; field-level reasons in `details.violations` |
| DEST_RULE_FREQUENCY_CAP | later | Frequency cap reached |
| CONNECTION_AUTH_EXPIRED | no (after reconnect) | Token expired or revoked |
| PLATFORM_RATE_LIMIT | yes | Platform said slow down; `details.retry_after_s` holds the reset time |
| PLATFORM_QUOTA_EXHAUSTED | next window | Daily quota used |
| PLATFORM_CONTENT_REJECTED | no | Platform refused the content |
| PLATFORM_UNAVAILABLE | yes | Timeout or 5xx |
| CONNECTOR_DISABLED | no | Kill switch on |
| VALIDATION_ERROR, NOT_FOUND, UNKNOWN_CONNECTOR, METHOD_NOT_SUPPORTED, CONNECTION_INVALID | no | Request problems |
| MISSING_IDEMPOTENCY_KEY, IDEMPOTENCY_KEY_REUSED | no | Idempotency header problems |
| INTERNAL_ERROR | no | Unexpected failure |

## Posting rules (checked before every post)
A destination's rules are data in `destination.config.rules`:
```json
"rules": {
  "frequency_cap": {"max_posts": 1, "window_hours": 168},
  "self_promo_allowed": false,
  "link_policy": {"allowed": true, "max_links": 2},
  "disclosure_required": true
}
```
| Rule | Outcome |
|---|---|
| Promotional post, `self_promo_allowed: false` | `blocked`, `DEST_RULE_SELF_PROMOTION` |
| Links not allowed or over `max_links` (the canonical URL counts) | `blocked`, `DEST_RULE_LINK_POLICY` |
| Frequency cap reached | `rescheduled`, `DEST_RULE_FREQUENCY_CAP`, with `reschedule_at` = when a slot opens |
| `disclosure_required` and content is AI-generated | Disclosure line appended once, reported in `warnings` |

Order per target: replay check, rules, destination format limits, then publish. A blocked or rescheduled post is
never sent to the platform. Known limit: two simultaneous posts to one capped destination could both pass the cap check.

## How retries stay safe
1. The same `Idempotency-Key` + same body returns the same job (`Idempotent-Replay: true`); different body gives `409`.
2. Each post is recorded under a unique `(destination_id, idempotency_key)`; a replay returns the stored post.
3. The key is also sent to the platform (`Idempotency-Key` header) so the platform can dedupe.

## Secrets
Credentials arrive in `connection`, are used in memory only, and are stored redacted. Logs contain method, path and
status only. Tests check the database, job responses and logs for leaks.
