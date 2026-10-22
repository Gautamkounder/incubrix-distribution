"""HTTP API. Everything under /api/v1/, plus the connector contract at /connector/v1/ (Appendix A)."""
import hashlib
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Header, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.connectors.registry import get_registry
from app.db import IdempotencyRecord, Job, get_engine, session_scope
from app.errors import AppError, ErrorCode
from app.schemas import Destination, JobAccepted, JobStatus, PublishRequest, Rendition
from app.security import redact
from app.services.publisher import run_job
from app.storage import Storage

api = APIRouter(prefix="/api/v1")
contract = APIRouter(prefix="/connector/v1")
root = APIRouter()


# ---------- health ----------
@root.get("/health", tags=["ops"])
@api.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok"}


@root.get("/ready", tags=["ops"])
@api.get("/ready", tags=["ops"])
def ready() -> dict:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise AppError(ErrorCode.INTERNAL_ERROR, "database not reachable", status_code=503)
    return {"status": "ready", "connectors": sorted(get_registry().connectors)}


# ---------- connectors ----------
@api.get("/connectors", tags=["connectors"])
def list_connectors() -> list[dict]:
    return [c.manifest.model_dump() for c in get_registry().connectors.values()]


# ---------- publish + jobs ----------
def _hash_request(req: PublishRequest) -> str:
    return hashlib.sha256(json.dumps(req.model_dump(), sort_keys=True, default=str).encode()).hexdigest()


def _redacted(req: PublishRequest) -> dict:
    data = req.model_dump()
    for target in data["targets"]:
        target["connection"] = {k: "***" for k in target["connection"]}
    return redact(data)


@api.post("/publish", status_code=202, response_model=JobAccepted, tags=["publish"])
def publish(req: PublishRequest, background: BackgroundTasks, request: Request, response: Response,
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> JobAccepted:
    if not idempotency_key:
        raise AppError(ErrorCode.MISSING_IDEMPOTENCY_KEY, "Send an Idempotency-Key header with every POST")
    registry = get_registry()
    for target in req.targets:
        registry.get(target.destination.connector_key)  # unknown connector -> clear error before any job exists

    req_hash = _hash_request(req)
    correlation = request.headers.get("X-Correlation-Id", "-")
    try:
        with session_scope() as db:
            existing = db.get(IdempotencyRecord, idempotency_key)
            if existing:
                if existing.request_hash != req_hash:
                    raise AppError(ErrorCode.IDEMPOTENCY_KEY_REUSED,
                                   "This Idempotency-Key was already used with a different request")
                job_id, is_new = existing.job_id, False
            else:
                import uuid
                job_id, is_new = uuid.uuid4().hex, True
                db.add(Job(id=job_id, status="queued", progress=0, request=_redacted(req),
                           correlation_id=correlation, idempotency_key=idempotency_key, callback_url=req.callback_url))
                db.flush()
                db.add(IdempotencyRecord(key=idempotency_key, request_hash=req_hash, job_id=job_id))
    except IntegrityError:  # two identical requests raced: the loser returns the winner's job
        with session_scope() as db:
            job_id, is_new = db.get(IdempotencyRecord, idempotency_key).job_id, False

    if is_new:
        background.add_task(run_job, job_id, req.model_dump())
    else:
        response.headers["Idempotent-Replay"] = "true"  # same job, work is never done twice
    return JobAccepted(job_id=job_id, status="queued" if is_new else _status_of(job_id),
                       status_url=f"/api/v1/jobs/{job_id}")


def _status_of(job_id: str) -> str:
    with session_scope() as db:
        return db.get(Job, job_id).status


@api.get("/jobs/{job_id}", response_model=JobStatus, tags=["publish"])
def get_job(job_id: str) -> JobStatus:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise AppError(ErrorCode.NOT_FOUND, f"Job '{job_id}' not found")
        links = {"self": f"/api/v1/jobs/{job.id}"}
        if job.result and job.result.get("manifest_url"):
            links["manifest"] = job.result["manifest_url"]
        return JobStatus(job_id=job.id, status=job.status, progress=job.progress, result=job.result,
                         error=job.error, links=links, created_at=job.created_at, updated_at=job.updated_at)


@api.get("/files/{path:path}", tags=["files"])
def get_file(path: str):
    found = Storage(get_settings()).read_local(path)
    if found is None:
        raise AppError(ErrorCode.NOT_FOUND, "File not found")
    return FileResponse(found)


# ---------- connector contract: POST /connector/v1/{connector_key}/{method} ----------
METHOD_CAPABILITY = {"publish": "publish", "get_status": "status", "delete": "delete",
                     "fetch_metrics": "metrics", "build_assist_pack": "assist", "refresh_auth": "refresh_auth"}


@contract.post("/{connector_key}/{method}", tags=["connector-contract"])
def call_connector(connector_key: str, method: str, body: dict[str, Any] = Body(...)) -> Any:
    connector = get_registry().get(connector_key)
    if method != "validate" and method not in METHOD_CAPABILITY:
        raise AppError(ErrorCode.NOT_FOUND, f"Unknown method '{method}'", details={"methods": ["validate", *METHOD_CAPABILITY]})
    if method in METHOD_CAPABILITY and METHOD_CAPABILITY[method] not in connector.manifest.capabilities:
        raise connector._unsupported(method)
    try:
        if method in ("validate", "publish", "build_assist_pack"):
            rendition, destination = Rendition(**body["rendition"]), Destination(**body["destination"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Bad request body", details={"reason": str(exc)[:200]})
    connection = body.get("connection", {})
    if method == "validate":
        return connector.validate(rendition, destination, connection)
    if method == "publish":
        return connector.publish(rendition, destination, connection, body.get("idempotency_key", ""))
    if method == "build_assist_pack":
        return connector.build_assist_pack(rendition, destination)
    if method == "get_status":
        return connector.get_status(body["platform_post_id"], connection)
    if method == "delete":
        return connector.delete(body["platform_post_id"], connection)
    if method == "fetch_metrics":
        return connector.fetch_metrics(body["platform_post_id"], connection, body.get("since"))
    return connector.refresh_auth(connection)
