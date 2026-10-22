"""Run the certification harness against one destination.

Usage: python -m tools.certify --target my_target.json --out evidence
my_target.json looks like:
  {"destination": {"id": "d1", "connector_key": "webhook", "config": {}},
   "connection": {"endpoint": "https://partner.example/hook", "secret": "..."}}
"""
import argparse
import json
import sys
from pathlib import Path

from app.certification import certify
from app.connectors.registry import get_registry
from app.schemas import PublishTarget


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--out", default="evidence")
    args = parser.parse_args()

    target = PublishTarget.model_validate(json.loads(Path(args.target).read_text(encoding="utf-8")))
    connector = get_registry().get(target.destination.connector_key)
    result = certify(connector, target.destination, target.connection, evidence_dir=args.out)
    print(json.dumps({"certified": result["certified"],
                      "steps": {s["step"]: s["ok"] for s in result["steps"]},
                      "evidence_file": result.get("evidence_file")}))
    return 0 if result["certified"] else 1


if __name__ == "__main__":
    sys.exit(main())