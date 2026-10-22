"""Loads every manifest in the manifests folder and builds one connector per manifest."""
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings
from app.connectors.assisted import AssistedConnector
from app.connectors.base import Connector, load_manifest
from app.connectors.mock_platform import make_mock_transport
from app.connectors.webhook import WebhookConnector
from app.errors import AppError, ErrorCode

CONNECTOR_CLASSES: dict[str, type[Connector]] = {
    "webhook": WebhookConnector,
    "assisted": AssistedConnector,
}


class Registry:
    def __init__(self, settings: Settings):
        self.connectors: dict[str, Connector] = {}
        transport = make_mock_transport() if settings.simulation_mode else None
        for path in sorted(Path(settings.manifests_dir).glob("*.yaml")):
            manifest = load_manifest(path)
            cls = CONNECTOR_CLASSES.get(manifest.key)
            if cls is None:
                raise RuntimeError(f"manifest '{manifest.key}' has no connector class")
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
