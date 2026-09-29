from dataclasses import replace
from pathlib import Path
import sys

from config import MonitorConfig
from metrics import MetricStatus, MetricsSnapshot
from service import MonitorService


FACE_SERVICE_ROOT = Path(__file__).resolve().parents[3] / "bmo-face"
if str(FACE_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(FACE_SERVICE_ROOT))

from face.state_machine import Event, FaceState, FaceStateMachine


def _snapshot(cpu, temperature, disk):
    return MetricsSnapshot(
        sampled_at="2026-09-29T00:00:00+00:00",
        cpu=MetricStatus(cpu is not None, {"percent": cpu}),
        ram=MetricStatus(
            True,
            {"total_bytes": 1000, "available_bytes": 500, "used_percent": 50.0},
        ),
        temperature=MetricStatus(
            temperature is not None,
            {"celsius": temperature, "source": "cpu_thermal"},
        ),
        disk=MetricStatus(disk is not None, {"path": "/", "free_bytes": disk}),
        wifi=MetricStatus(True, {"connected": True}),
        bluetooth=MetricStatus(True, {"present": True, "powered": True}),
    )


class FakeProvider:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self.calls = 0

    def sample(self):
        self.calls += 1
        return next(self.snapshots)


class FakeMqttClient:
    def __init__(self):
        self.emotions = []
        self.clears = 0
        self.connected = False
        self.stopped = False

    def connect(self):
        self.connected = True

    def set_emotion(self, emotion):
        self.emotions.append(emotion)

    def clear_emotion(self):
        self.clears += 1

    def stop(self):
        self.stopped = True


def _service(snapshots):
    provider = FakeProvider(snapshots)
    mqtt = FakeMqttClient()
    config = replace(MonitorConfig(), sample_interval_seconds=5.0)
    service = MonitorService(
        config,
        provider=provider,
        mqtt_client=mqtt,
        monotonic_fn=lambda: 0.0,
    )
    return service, provider, mqtt


def test_monitor_publishes_initial_and_reasserted_emotion():
    service, provider, mqtt = _service(
        [_snapshot(10.0, 55.0, 600_000_000), _snapshot(10.0, 55.0, 600_000_000)]
    )

    service._tick(0.0)
    service._tick(1.99)
    assert mqtt.emotions == ["happy"]
    service._tick(2.0)
    assert mqtt.emotions == ["happy", "happy"]
    service._tick(5.0)
    assert provider.calls == 2
    assert mqtt.emotions[-1] == "happy"


def test_reassertions_keep_m2_emotion_active_past_transient_timeout():
    service, _, mqtt = _service([_snapshot(90.0, 55.0, 600_000_000)] * 2)
    current_time = [0.0]
    face = FaceStateMachine(
        now_fn=lambda: current_time[0],
        random_fn=lambda lower, upper: upper,
    )
    processed = 0

    for second in range(10):
        current_time[0] = float(second)
        service._tick(current_time[0])
        while processed < len(mqtt.emotions):
            face.handle_event(
                Event("bmo/system/state", {"emotion": mqtt.emotions[processed]})
            )
            processed += 1
        face.tick()

    assert mqtt.emotions == ["stressed"] * 5
    assert face.state == FaceState.STRESSED


def test_monitor_changes_emotion_immediately_and_clears_when_required_metric_fails():
    service, provider, mqtt = _service(
        [
            _snapshot(10.0, 55.0, 600_000_000),
            _snapshot(10.0, 72.0, 600_000_000),
            _snapshot(None, 55.0, 600_000_000),
        ]
    )

    service._tick(0.0)
    service._tick(5.0)
    assert mqtt.emotions == ["happy", "hot"]
    service._tick(10.0)

    assert provider.calls == 3
    assert mqtt.clears == 1
    assert service.status()["status"] == "degraded"
    assert service.status()["emotion"] is None


def test_optional_metric_unavailability_does_not_degrade_health():
    service, _, _ = _service([_snapshot(10.0, 55.0, 600_000_000)])
    service._tick(0.0)
    status = service.status()
    assert status["healthy"] is True
    assert status["metrics"]["cpu"]["available"] is True


def test_unavailable_required_metric_does_not_publish_happy():
    service, _, mqtt = _service([_snapshot(None, 55.0, 600_000_000)])

    service._tick(0.0)

    assert mqtt.emotions == []
    assert service.status()["status"] == "degraded"


def test_request_stop_sets_stop_event():
    service, _, mqtt = _service([_snapshot(10.0, 55.0, 600_000_000)])

    service.request_stop()

    assert service._stop_event.is_set()
    service.stop()
    assert mqtt.stopped
