import json
from pathlib import Path

import yaml

from tools.batch_runner import run_batch


def test_batch_runner_runs_all_samples(client, tmp_path):
    files = sorted(Path("samples").glob("*.json"))
    summary = run_batch(client, files, tmp_path / "out")
    assert summary["total"] == len(files) == 6
    assert summary["failed"] == 0  # job-level success; per-destination failures are in the results
    assert (tmp_path / "out" / "summary.json").exists()
    rate = json.loads((tmp_path / "out" / "03_webhook_rate_limited.result.json").read_text())
    assert rate["result"]["destinations"][0]["error"]["code"] == "PLATFORM_RATE_LIMIT"
    long_title = json.loads((tmp_path / "out" / "04_title_too_long.result.json").read_text())
    assert long_title["result"]["destinations"][0]["status"] == "blocked"


def test_openapi_yaml_matches_running_service(client):
    from app.main import app
    checked_in = yaml.safe_load(Path("openapi.yaml").read_text(encoding="utf-8"))
    assert checked_in == json.loads(json.dumps(app.openapi())), "run: python -m tools.export_openapi"
    assert str(checked_in["openapi"]).startswith("3.1")
    assert all(p.startswith(("/api/v1", "/connector/v1", "/health", "/ready")) for p in checked_in["paths"])


def test_batch_runner_rule_samples(client, tmp_path):
    files = sorted(Path("samples").glob("*.json"))
    run_batch(client, files, tmp_path / "out")
    promo = json.loads((tmp_path / "out" / "05_promo_to_no_promo.result.json").read_text())
    assert promo["result"]["destinations"][0]["error"]["code"] == "DEST_RULE_SELF_PROMOTION"
    disc = json.loads((tmp_path / "out" / "06_ai_disclosure.result.json").read_text())
    assert disc["result"]["destinations"][0]["status"] == "published"
    assert any("ai_disclosure" in w for w in disc["result"]["manifest"]["warnings"])
