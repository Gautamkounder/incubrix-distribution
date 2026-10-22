"""IncuBrix Long-Tail Distribution connector service."""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import init_db
from app.errors import AppError, ErrorCode
from app.logging_setup import correlation_id_var, get_logger, log_extra, setup_logging
from app.routes import api, contract, root

log = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(get_settings().log_level)
    init_db()
    yield


app = FastAPI(title="IncuBrix Long-Tail Distribution", version="0.1.0", lifespan=lifespan,
              description="Connector service: publishes content to forums, blogs and partner sites with safe retries.")
app.include_router(root)
app.include_router(api)
app.include_router(contract)


@app.middleware("http")
async def correlation_and_access_log(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex
    token = correlation_id_var.set(cid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        correlation_id_var.reset(token)
    response.headers["X-Correlation-Id"] = cid
    # Log method, path and status only. Never headers or bodies, because those can carry tokens.
    correlation_id_var.set(cid)
    log.info("request", extra=log_extra(method=request.method, path=request.url.path, status=response.status_code,
                                        ms=int((time.perf_counter() - started) * 1000)))
    return response


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    details = {"fields": [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]}
    err = AppError(ErrorCode.VALIDATION_ERROR, "Request failed validation", details=details)
    return JSONResponse(status_code=422, content=err.to_dict())


@app.exception_handler(StarletteHTTPException)
async def http_handler(_: Request, exc: StarletteHTTPException):
    code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.VALIDATION_ERROR
    return JSONResponse(status_code=exc.status_code, content=AppError(code, str(exc.detail)).to_dict())


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content=AppError(ErrorCode.INTERNAL_ERROR, "Internal error").to_dict())
