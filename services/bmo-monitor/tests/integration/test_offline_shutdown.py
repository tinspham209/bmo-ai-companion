from dataclasses import replace
import socket
from threading import Thread
import time

from config import MonitorConfig
from metrics import MetricStatus, MetricsSnapshot
from mqtt_client import MonitorMqttClient
from service import MonitorService


class FakeProvider:
    def sample(self):
        return MetricsSnapshot(
            sampled_at="2026-09-29T00:00:00+00:00",
            cpu=MetricStatus(True, {"percent": 10.0}),
            ram=MetricStatus(
                True,
                {"total_bytes": 1000, "available_bytes": 500, "used_percent": 50.0},
            ),
            temperature=MetricStatus(
                True, {"celsius": 55.0, "source": "cpu_thermal"}
            ),
            disk=MetricStatus(True, {"path": "/", "free_bytes": 600_000_000}),
            wifi=MetricStatus(False, {"connected": None}, "unavailable"),
            bluetooth=MetricStatus(
                False, {"present": None, "powered": None}, "unavailable"
            ),
        )


def test_shutdown_is_bounded_when_mqtt_broker_is_unavailable():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    config = replace(MonitorConfig(), mqtt_broker="127.0.0.1", mqtt_port=port)
    service = MonitorService(
        config,
        provider=FakeProvider(),
        mqtt_client=MonitorMqttClient("127.0.0.1", port),
    )
    worker = Thread(target=service.run)
    worker.start()
    time.sleep(0.1)
    started = time.monotonic()
    service.stop()
    worker.join(timeout=5.0)
    elapsed = time.monotonic() - started

    assert not worker.is_alive()
    assert elapsed < 5.0
