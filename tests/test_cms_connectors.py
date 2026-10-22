from pathlib import Path
import pytest

from app.certification import certify
from app.config import get_settings
from app.connectors.base import load_manifest
from app.connectors.ghost import GhostConnector
from app.connectors.lemmy import LemmyConnector
from app.connectors.mock_cms import make_cms_transport
from app.errors import AppError, ErrorCode
from app.schemas import Destination, Rendition

MANIFESTS = Path(__file__).resolve().parent.parent / "app" / "connectors" / "manifests"

G_DEST = Destination(id="ghost-1", connector_key="ghost")
G_CONN = {"endpoint": "https://blog.example", "admin_api_key": "ghost-key"}

L_DEST = Destination(id="lemmy-1", connector_key="lemmy", config={"community_id": 2})
L_CONN = {"endpoint": "https://lemmy.example", "auth_jwt": "jwt-token"}

def make(cls, name):
    return cls(load_manifest(MANIFESTS / f"{name}.yaml"), get_settings(), transport=make_cms_transport())

def test_ghost_passes_certification():
    res = certify(make(GhostConnector, "ghost"), G_DEST, G_CONN)
    assert res["certified"] is True

def test_lemmy_passes_certification():
    res = certify(make(LemmyConnector, "lemmy"), L_DEST, L_CONN)
    assert res["certified"] is True

def test_ghost_missing_credentials():
    c = make(GhostConnector, "ghost")
    with pytest.raises(AppError) as e:
        c.publish(Rendition(title="T", body="B"), G_DEST, {"endpoint": "https://blog.example"}, "k")
    assert e.value.code == ErrorCode.CONNECTION_INVALID

def test_lemmy_missing_credentials():
    c = make(LemmyConnector, "lemmy")
    with pytest.raises(AppError) as e:
        c.publish(Rendition(title="T", body="B"), L_DEST, {"endpoint": "https://lemmy.example"}, "k")
    assert e.value.code == ErrorCode.CONNECTION_INVALID
