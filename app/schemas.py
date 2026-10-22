"""Request and response shapes."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Rendition(BaseModel):
    """The content to publish, already adapted for one destination (tailoring comes later)."""
    title: str
    body: str
    canonical_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)
    language: str = "en"
    is_promotional: bool = False
    ai_generated: bool = False


class Destination(BaseModel):
    id: str
    connector_key: str
    surface: str | None = None
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class PublishTarget(BaseModel):
    destination: Destination
    connection: dict[str, Any] = Field(default_factory=dict)  # credentials; never stored or logged


class PublishRequest(BaseModel):
    rendition: Rendition
    targets: list[PublishTarget] = Field(min_length=1, max_length=50)
    callback_url: str | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: str
    status_url: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | running | succeeded | failed
    progress: int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    links: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
