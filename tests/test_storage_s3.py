"""S3 path logic tested with a fake client (no real S3 needed)."""
from botocore.exceptions import ClientError

from app.config import Settings
from app.storage import Storage


class FakeS3:
    def __init__(self):
        self.buckets, self.objects = set(), {}

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "404", "Message": "nope"}}, "HeadBucket")

    def create_bucket(self, Bucket):
        self.buckets.add(Bucket)

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"http://localhost:9000/{Params['Bucket']}/{Params['Key']}?sig=x"


def test_s3_backend_creates_bucket_and_returns_link(monkeypatch):
    fake = FakeS3()
    storage = Storage(Settings(storage_backend="s3", s3_endpoint_url="http://rustfs:9000", s3_bucket="outs"))
    monkeypatch.setattr(storage, "_client", lambda endpoint: fake)
    url = storage.put_json("jobs/j1/manifest.json", {"a": 1})
    assert "outs" in fake.buckets
    assert ("outs", "jobs/j1/manifest.json") in fake.objects
    assert url.startswith("http://localhost:9000/outs/jobs/j1/manifest.json")


def test_local_storage_blocks_path_traversal(tmp_path):
    storage = Storage(Settings(local_storage_dir=str(tmp_path / "s")))
    storage.put_bytes("a/b.txt", b"hi")
    assert storage.read_local("a/b.txt") is not None
    assert storage.read_local("../../etc/passwd") is None
