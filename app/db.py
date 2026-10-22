"""Database: jobs, idempotency keys, publications. SQLite for local/tests, Postgres in docker compose."""
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    request: Mapped[dict] = mapped_column(JSON)  # stored with credentials redacted
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), default="-")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    callback_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Publication(Base):
    """One row per real post. The unique constraint is what makes retries safe."""
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("destination_id", "idempotency_key", name="uq_dest_idem"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(40))
    destination_id: Mapped[str] = mapped_column(String(200))
    connector_key: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(300))
    platform_post_id: Mapped[str] = mapped_column(String(300))
    live_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engines: dict = {}
_sessionmakers: dict = {}


def get_engine():
    url = get_settings().database_url
    if url not in _engines:
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
            _engines[url] = create_engine(url, **kwargs)
        else:
            _engines[url] = create_engine(url, pool_pre_ping=True)
    return _engines[url]


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    engine = get_engine()
    maker = _sessionmakers.setdefault(engine, sessionmaker(bind=engine, expire_on_commit=False))
    session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
