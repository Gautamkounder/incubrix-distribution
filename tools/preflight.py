"""Pre-flight check tool to ensure all manifests load, connectors register, and DB connects."""
import sys
from sqlalchemy import text
from app.config import get_settings
from app.connectors.registry import get_registry
from app.db import session_scope

def main() -> int:
    print("Running pre-flight checks...")
    settings = get_settings()
    print(f"  Configuration loaded (Simulation Mode: {settings.simulation_mode})")

    registry = get_registry()
    print(f"  Connectors registered: {', '.join(sorted(registry.connectors.keys()))}")

    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        print("  Database connection: OK")
    except Exception as e:
        print(f"  Database connection FAILED: {e}")
        return 1

    print("Pre-flight check PASSED.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
