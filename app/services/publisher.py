"""Runs one publish job: for each target -> validate -> (rules, Day 2) -> publish or assist pack -> record."""
import json
import time

import httpx

from app.config import get_settings
from app.connectors.registry import get_registry
from datetime import timedelta

from app import rules as rules_engine
from app.db import Job, Publication, session_scope, utcnow
from app.errors import AppError, ErrorCode
from app.logging_setup import correlation_id_var, get_logger, job_id_var, log_extra
from app.schemas import PublishRequest
from app.security import sign
from app.storage import Storage

log = get_logger("publisher")


def _result_base(target) -> dict:
    return {"destination_id": target.destination.id, "connector_key": target.destination.connector_key}


def _process_target(target, request: PublishRequest, job_idem_key: str, job_id: str, storage: Storage) -> dict:
    registry = get_registry()
    dest, conn = target.destination, target.connection
    base = _result_base(target)
    try:
        connector = registry.get(dest.connector_key)
        assisted = connector.manifest.tier == "assisted"
        idem_key = f"{job_idem_key}:{dest.id}"

        # 1. Safe retries come first: a repeated key must return the stored post, never be blocked by its own cap.
        if not assisted:
            with session_scope() as db:
                existing = db.query(Publication).filter_by(destination_id=dest.id, idempotency_key=idem_key).first()
            if existing:
                return {**base, "status": "published", "platform_post_id": existing.platform_post_id,
                        "live_url": existing.live_url, "replayed": True, "warnings": []}

        # 2. Posting rules (checked before every post).
        now = utcnow()
        recent: list = []
        window = rules_engine.cap_window_hours(dest)
        if window is not None and not assisted:  # we cannot see manual posts, so assisted skips the cap
            with session_scope() as db:
                rows = (db.query(Publication.created_at)
                        .filter(Publication.destination_id == dest.id,
                                Publication.created_at >= now - timedelta(hours=window)).all())
            recent = [r[0] for r in rows]
        decision = rules_engine.evaluate(request.rendition, dest, recent, now)
        warnings = list(decision.notes)
        if decision.action == "block":
            err = decision.violation.to_error()
            return {**base, "status": "blocked", "rules_checked": decision.checked, "warnings": warnings, **err.to_dict()}
        if decision.action == "reschedule":
            err = decision.violation.to_error()
            return {**base, "status": "rescheduled", "reschedule_at": decision.reschedule_at.isoformat(),
                    "rules_checked": decision.checked, "warnings": warnings, **err.to_dict()}
        rendition = decision.rendition

        # 3. Format limits of the destination.
        check = connector.validate(rendition, dest, conn)
        if not check["ok"]:
            err = AppError(ErrorCode.DEST_SPEC_VIOLATION, "Content breaks the destination's format limits",
                           details={"violations": check["violations"]})
            return {**base, "status": "blocked", "rules_checked": decision.checked, "warnings": warnings, **err.to_dict()}

        # 4. Assisted destinations get a ready-to-post pack instead of an API call.
        if assisted:
            pack = connector.build_assist_pack(rendition, dest)
            files = []
            for f in pack["files"]:
                url = storage.put_bytes(f"jobs/{job_id}/{dest.id}/{f['name']}", f["content"].encode(), f["content_type"])
                files.append({"name": f["name"], "url": url})
            return {**base, "status": "assist_pack", "rules_checked": decision.checked, "warnings": warnings,
                    "assist_pack": {"caption": pack["caption"], "deep_link": pack["deep_link"],
                                    "checklist": pack["checklist"], "files": files}}

        # 5. Publish and record.
        res = connector.publish(rendition, dest, conn, idem_key)
        with session_scope() as db:
            db.add(Publication(job_id=job_id, destination_id=dest.id, connector_key=connector.key,
                               idempotency_key=idem_key, platform_post_id=res["platform_post_id"],
                               live_url=res.get("live_url")))
        return {**base, "status": "published", "platform_post_id": res["platform_post_id"],
                "live_url": res.get("live_url"), "rules_checked": decision.checked, "warnings": warnings}
    except AppError as exc:
        log.warning("target failed", extra=log_extra(destination=dest.id, code=exc.code.value))
        return {**base, "status": "failed", "warnings": [], **exc.to_dict()}


def _build_manifest(job_id: str, request: PublishRequest, results: list[dict], timings_ms: int) -> dict:
    registry = get_registry()
    used = sorted({r["connector_key"] for r in results})
    return {
        "job_id": job_id,
        "connectors": [{"key": k, "version": registry.get(k).manifest.version, "tier": registry.get(k).manifest.tier}
                       for k in used if k in registry.connectors],
        "models": [],  # no AI model used in the publish path yet (Day 2: rules capture / tailoring will list theirs)
        "settings": {"simulation_mode": get_settings().simulation_mode},
        "seed": None,
        "timings_ms": {"total": timings_ms},
        "cost_estimate_usd": 0.0,
        "warnings": [f"{r['destination_id']}: {r['error']['code']}" for r in results if "error" in r]
                    + [f"{r['destination_id']}: {w}" for r in results for w in r.get("warnings", [])],
        "rights": {"content_source": "supplied by caller", "ai_generated": request.rendition.ai_generated},
    }


def _send_callback(url: str, payload: dict) -> None:
    body = json.dumps(payload, default=str, sort_keys=True).encode()
    try:
        httpx.post(url, content=body, timeout=get_settings().http_timeout_s,
                   headers={"Content-Type": "application/json",
                            "X-IncuBrix-Signature": sign(get_settings().callback_secret, body)})
    except httpx.HTTPError as exc:
        log.warning("callback failed", extra=log_extra(reason=type(exc).__name__))


def run_job(job_id: str, request_dict: dict) -> None:
    """request_dict still holds credentials (in memory only). The database row stores a redacted copy."""
    request = PublishRequest.model_validate(request_dict)
    with session_scope() as db:
        job = db.get(Job, job_id)
        job.status, job.progress = "running", 5
        correlation, idem_key, callback = job.correlation_id, job.idempotency_key, job.callback_url
    job_id_var.set(job_id)
    correlation_id_var.set(correlation)
    storage = Storage(get_settings())
    started = time.perf_counter()
    try:
        results = []
        total = len(request.targets)
        for i, target in enumerate(request.targets, start=1):
            results.append(_process_target(target, request, idem_key, job_id, storage))
            with session_scope() as db:
                db.get(Job, job_id).progress = 10 + int(80 * i / total)
        elapsed = int((time.perf_counter() - started) * 1000)
        manifest = _build_manifest(job_id, request, results, elapsed)
        manifest_url = storage.put_json(f"jobs/{job_id}/manifest.json", manifest)
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.status, job.progress = "succeeded", 100
            job.result = {"destinations": results, "manifest": manifest, "manifest_url": manifest_url}
            job.updated_at = utcnow()
        log.info("job finished", extra=log_extra(destinations=total, ms=elapsed))
    except Exception as exc:  # never leave a job stuck in "running"
        log.exception("job crashed")
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.status = "failed"
            job.error = AppError(ErrorCode.INTERNAL_ERROR, "Job crashed", details={"type": type(exc).__name__}).to_dict()["error"]
    if callback:
        with session_scope() as db:
            job = db.get(Job, job_id)
            payload = {"job_id": job_id, "status": job.status, "progress": job.progress}
        _send_callback(callback, payload)
