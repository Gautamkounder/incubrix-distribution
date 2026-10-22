"""Files out: local folder (default) or any S3-compatible store (MinIO in docker compose)."""
import json
from pathlib import Path

from app.config import Settings


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._s3 = None
        self._s3_public = None

    # ---- public API ----
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        if self.settings.storage_backend == "s3":
            return self._put_s3(key, data, content_type)
        return self._put_local(key, data)

    def put_json(self, key: str, payload: dict) -> str:
        return self.put_bytes(key, json.dumps(payload, indent=2, default=str).encode(), "application/json")

    def read_local(self, key: str) -> Path | None:
        root = Path(self.settings.local_storage_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents or not path.is_file():  # blocks ../ path traversal
            return None
        return path

    # ---- backends ----
    def _put_local(self, key: str, data: bytes) -> str:
        root = Path(self.settings.local_storage_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("invalid storage key")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"{self.settings.public_base_url}/api/v1/files/{key}"

    def _client(self, endpoint: str):
        import boto3  # imported lazily so local mode needs no S3
        return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=self.settings.s3_access_key,
                            aws_secret_access_key=self.settings.s3_secret_key, region_name="us-east-1")

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError
        try:
            self._s3.head_bucket(Bucket=self.settings.s3_bucket)
        except ClientError:
            self._s3.create_bucket(Bucket=self.settings.s3_bucket)  # no separate "create bucket" container needed

    def _put_s3(self, key: str, data: bytes, content_type: str) -> str:
        if self._s3 is None:
            self._s3 = self._client(self.settings.s3_endpoint_url)
            public = self.settings.s3_public_endpoint_url or self.settings.s3_endpoint_url
            self._s3_public = self._client(public)  # presigned links must use a host the user can reach
            self._ensure_bucket()
        self._s3.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
        return self._s3_public.generate_presigned_url(
            "get_object", Params={"Bucket": self.settings.s3_bucket, "Key": key}, ExpiresIn=3600)
