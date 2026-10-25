# IncuBrix Long-Tail Distribution: connector service

Publishes one piece of content to many small destinations (forums, blogs, partner sites), following the IncuBrix connector contract. One connector serves many destinations; a destination is data, not code.

**Status: Complete (Core + Advanced Tiers).** Working: API, jobs, idempotency, error codes, logging, storage, webhook (HMAC), assisted packs, posting-rules engine, dynamic content tailoring, automated retries with exponential backoff, certification harness, and catalogue tools. 
**Connectors (9):** Webhook, Assisted, Discourse, Dev.to, Ghost, Lemmy, Hashnode, Slack, MRSS.

## Run it (Windows PowerShell or any shell)
```bash
copy .env.example .env
docker compose up --build
```
Without Docker:
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tests (no API keys needed)
Runs the complete suite of 76 tests covering rules, retries, connectors, and API contracts.
```bash
pytest
```

## Tools & Utilities
**Batch Runner:**
```bash
python -m tools.batch_runner --input samples --out batch_out --api-url http://localhost:8000
```
**Pre-flight Check:**
```bash
python -m tools.preflight
```
**Catalogue Importer (Advanced Tier):** 
Demonstrates processing 1,000 destinations in <5 minutes with relevance scoring and simulated AI-capture rules.
```bash
python -m tools.catalogue_importer --mock
```

## API (all under /api/v1/)
| Route | Purpose |
|---|---|
| `POST /api/v1/publish` | Needs an `Idempotency-Key` header. Returns `202` + `job_id`. |
| `GET /api/v1/jobs/{job_id}` | `status` (queued, running, succeeded, failed), `progress` 0-100, results, manifest link |
| `GET /api/v1/connectors` | Loaded connector manifests |
| `POST /connector/v1/{connector_key}/{method}` | Connector contract: validate, publish, get_status, delete, fetch_metrics, refresh_auth, build_assist_pack |
| `GET /health`, `GET /ready` | Also available under `/api/v1/` |

## Settings
Every setting is an environment variable. See `.env.example` (nothing is hard-coded). `SIMULATION_MODE=true` uses mock platforms (injecting `httpx.MockTransport`), so everything runs with no real accounts. 

## Error codes
Every error is `{"error": {"code", "message", "retryable", "details"}}`.

| Code | Retryable | Meaning |
|---|---|---|
| DEST_SPEC_VIOLATION | no | Content breaks the destination's format limits |
| DEST_RULE_FREQUENCY_CAP | later | Frequency cap reached |
| CONNECTION_AUTH_EXPIRED | no | Token expired or revoked |
| PLATFORM_RATE_LIMIT | yes | Platform said slow down; system automatically retries |
| PLATFORM_QUOTA_EXHAUSTED | next window | Daily quota used |
| PLATFORM_CONTENT_REJECTED | no | Platform refused the content |
| PLATFORM_UNAVAILABLE | yes | Timeout or 5xx. System automatically retries |

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

Order per target: replay check, rules, destination format limits, then publish (with up to 3 retries for transient errors). A blocked or rescheduled post is never sent to the platform. 

## How retries stay safe
1. The same `Idempotency-Key` + same body returns the same job (`Idempotent-Replay: true`).
2. Each post is recorded under a unique `(destination_id, idempotency_key)`.
3. The key is also sent to the platform (`Idempotency-Key` header) so the remote platform can deduplicate.