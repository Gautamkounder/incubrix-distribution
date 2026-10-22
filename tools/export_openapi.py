"""Write openapi.yaml from the running app so the file always matches the service exactly."""
import json
from pathlib import Path

import yaml

from app.main import app

if __name__ == "__main__":
    spec = json.loads(json.dumps(app.openapi()))
    Path("openapi.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    print("wrote openapi.yaml,", len(spec["paths"]), "paths")
