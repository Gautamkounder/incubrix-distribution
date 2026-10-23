"""Loads every manifest in the manifests folder and builds one connector per manifest."""
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings
from app.connectors.assisted import AssistedConnector
from app.connectors.base import Connector, load_manifest
from app.connectors.devto import DevtoConnector
from app.connectors.discourse import DiscourseConnector
from app.connectors.ghost import GhostConnector
from app.connectors.lemmy import LemmyConnector
from app.connectors.hashnode import HashnodeConnector
from app.connectors.slack import SlackConnector
from app.connectors.mrss import MRSSConnector
from app.connectors.mock_cms import make_cms_transport
from app.connectors.mock_forums import make_forum_transport
from app.connectors.mock_platform import make_mock_transport
from app.connectors.mock_advanced import make_advanced_transport
from app.connectors.webhook import WebhookConnector
from app.errors import AppError, ErrorCode

CONNECTOR_CLASSES: dict[str, type[Connector]] = {
    "webhook": WebhookConnector,
    "assisted": AssistedConnector,
    "discourse": DiscourseConnector,
    "devto": DevtoConnector,
    "ghost": GhostConnector,
    "lemmy": LemmyConnector,
    "hashnode": HashnodeConnector,
    "slack": SlackConnector,
    "mrss": MRSSConnector,
}
FORUM_KEYS = {"discourse", "devto"}
CMS_KEYS = {"ghost", "lemmy"}
ADV_KEYS = {"hashnode", "slack", "mrss"}

class Registry:
    def __init__(self, settings: Settings):
        self.connectors: dict[str, Connector] = {}
        sim = settings.simulation_mode
        default_transport = make_mock_transport() if sim else None
        forum_transport = make_forum_transport() if sim else None
        cms_transport = make_cms_transport() if sim else None
        adv_transport = make_advanced_transport() if sim else None
        for path in sorted(Path(settings.manifests_dir).glob("*.yaml")):
            manifest = load_manifest(path)
            cls = CONNECTOR_CLASSES.get(manifest.key)
            if cls is None:
                raise RuntimeError(f"manifest '{manifest.key}' has no connector class")
            if manifest.key in FORUM_KEYS:
                transport = forum_transport
            elif manifest.key in CMS_KEYS:
                transport = cms_transport
            elif manifest.key in ADV_KEYS:
                transport = adv_transport
            else:
                transport = default_transport
            self.connectors[manifest.key] = cls(manifest, settings, transport)

    def get(self, key: str) -> Connector:
        if key not in self.connectors:
            raise AppError(ErrorCode.UNKNOWN_CONNECTOR, f"Unknown connector '{key}'",
                           details={"available": sorted(self.connectors)})
        return self.connectors[key]

@lru_cache
def _registry_for(simulation: bool, manifests_dir: str) -> Registry:
    return Registry(get_settings())

def get_registry() -> Registry:
    s = get_settings()
    return _registry_for(s.simulation_mode, s.manifests_dir)
