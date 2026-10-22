"""Batch runner: run a folder (or one file) of test inputs against the API and write every result to one folder.

    python -m tools.batch_runner --input samples --out batch_out --api-url http://localhost:8000
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def run_batch(client: httpx.Client, files: list[Path], out_dir: Path, timeout_s: float = 60.0) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"total": len(files), "succeeded": 0, "failed": 0, "items": []}
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        headers = {"Idempotency-Key": f"batch-{path.stem}", "X-Correlation-Id": f"batch-{path.stem}"}
        resp = client.post("/api/v1/publish", json=payload, headers=headers)
        record: dict = {"input": path.name, "http_status": resp.status_code}
        if resp.status_code == 202:
            job_id = resp.json()["job_id"]
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                job = client.get(f"/api/v1/jobs/{job_id}").json()
                if job["status"] in ("succeeded", "failed"):
                    break
                time.sleep(0.3)
            record.update(job_id=job_id, job_status=job["status"])
            (out_dir / f"{path.stem}.result.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
            ok = job["status"] == "succeeded"
        else:
            (out_dir / f"{path.stem}.result.json").write_text(resp.text, encoding="utf-8")
            ok = False
        summary["succeeded" if ok else "failed"] += 1
        summary["items"].append(record)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run test inputs against the API")
    parser.add_argument("--input", required=True, help="folder of .json inputs, or a single .json file")
    parser.add_argument("--out", default="batch_out")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    src = Path(args.input)
    files = sorted(src.glob("*.json")) if src.is_dir() else [src]
    with httpx.Client(base_url=args.api_url, timeout=30) as client:
        summary = run_batch(client, files, Path(args.out))
    print(json.dumps({k: v for k, v in summary.items() if k != "items"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
