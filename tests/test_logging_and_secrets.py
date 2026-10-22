import json
import logging

from app.logging_setup import JsonFormatter
from tests.conftest import publish, webhook_request


def test_logs_never_contain_the_secret(client, caplog):
    with caplog.at_level(logging.DEBUG):
        publish(client, webhook_request(simulate="429"))
        publish(client, webhook_request(), key="k2")
    assert "super-secret-value" not in caplog.text


def test_json_log_has_required_fields():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    out = json.loads(JsonFormatter().format(record))
    assert {"timestamp", "level", "message", "job_id", "correlation_id"} <= set(out)
