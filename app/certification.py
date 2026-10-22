"""Certification harness: prove a connector really works by running one full post lifecycle and saving the evidence.

Steps: validate -> publish -> confirm live -> delete -> confirm gone.
If a post was created, we always try to delete it, even when an earlier step failed.
Secrets are redacted before the evidence file is written.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.connectors.base import Connector
from app.errors import AppError
from app.schemas import Destination, Rendition

LIVE_STATUSES = {"live", "published", "active", "ok"}
GONE_STATUSES = {"deleted", "gone", "not_found", "removed"}
SECRET_HINTS = ("secret", "token", "password", "key", "authorization")


def _redact(connection: dict) -> dict:
    return {k: ("***" if any(h in k.lower() for h in SECRET_HINTS) else v) for k, v in connection.items()}


def _error(exc: AppError) -> dict:
    return exc.to_dict()["error"]


def default_rendition() -> Rendition:
    return Rendition(title="IncuBrix certification test",
                     body="Automated certification post. Safe to delete.",
                     tags=["certification"])


def certify(connector: Connector, destination: Destination, connection: dict,
            evidence_dir: str | Path | None = None, rendition: Rendition | None = None) -> dict:
    started = datetime.now(timezone.utc)
    rendition = rendition or default_rendition()
    idem_key = f"cert-{uuid.uuid4().hex[:12]}"
    steps: list[dict] = []
    state: dict = {"post_id": None}

    def run(name: str, fn) -> bool:
        t0 = time.perf_counter()
        try:
            ok, detail = fn()
        except AppError as exc:
            ok, detail = False, _error(exc)
        except Exception as exc:  # a crash is a failed step, not a crashed harness
            ok, detail = False, {"code": "HARNESS_ERROR", "message": f"{type(exc).__name__}: {exc}"}
        steps.append({"step": name, "ok": ok, "ms": int((time.perf_counter() - t0) * 1000), "detail": detail})
        return ok

    def validate():
        check = connector.validate(rendition, destination, connection)
        return check["ok"], check

    def publish():
        res = connector.publish(rendition, destination, connection, idem_key)
        state["post_id"] = res["platform_post_id"]
        return True, {**res, "idempotency_key": idem_key}

    def confirm_live():
        status = connector.get_status(state["post_id"], connection)
        return status.get("status") in LIVE_STATUSES, status

    def delete():
        return True, connector.delete(state["post_id"], connection)

    def confirm_gone():
        try:
            status = connector.get_status(state["post_id"], connection)
        except AppError as exc:
            err = _error(exc)
            gone = err.get("details", {}).get("platform_status") in (404, 410)
            return gone, err  # a 404/410 means gone; an outage does not prove anything
        return status.get("status") in GONE_STATUSES, {**status, "note": "post still reachable after delete"}

    if connector.manifest.tier == "assisted":
        steps.append({"step": "skipped", "ok": False, "ms": 0,
                      "detail": {"message": "assisted connectors have no API to certify; use the assist pack"}})
    else:
        if run("validate", validate) and run("publish", publish):
            run("confirm_live", confirm_live)
        if state["post_id"] and run("delete", delete):  # clean up even if confirm_live failed
            run("confirm_gone", confirm_gone)

    result = {
        "certified": bool(steps) and all(s["ok"] for s in steps),
        "connector": connector.key,
        "connector_version": connector.manifest.version,
        "destination_id": destination.id,
        "started_at": started.isoformat(),
        "post_id": state["post_id"],
        "connection": _redact(connection),
        "steps": steps,
    }
    if evidence_dir:
        folder = Path(evidence_dir)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{connector.key}_{destination.id}_{started:%Y%m%dT%H%M%SZ}.json"
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["evidence_file"] = str(path)
    return result