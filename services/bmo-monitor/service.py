"""Sampling loop and lifecycle for bmo-monitor."""

from __future__ import annotations

import threading
import time
from typing import Callable

from config import MonitorConfig
from metrics import MetricStatus, MetricsSnapshot, SystemMetricsProvider
from mqtt_client import MonitorMqttClient
from state import select_emotion


def empty_snapshot(disk_path: str = "/") -> MetricsSnapshot:
    return MetricsSnapshot(
        sampled_at="",
        cpu=MetricStatus(False, {"percent": None}, "not_sampled"),
        ram=MetricStatus(
            False,
            {"total_bytes": None, "available_bytes": None, "used_percent": None},
            "not_sampled",
        ),
        temperature=MetricStatus(
            False, {"celsius": None, "source": None}, "not_sampled"
        ),
        disk=MetricStatus(
            False, {"path": disk_path, "free_bytes": None}, "not_sampled"
        ),
        wifi=MetricStatus(False, {"connected": None}, "not_sampled"),
        bluetooth=MetricStatus(
            False, {"present": None, "powered": None}, "not_sampled"
        ),
    )


class MonitorService:
    def __init__(
        self,
        config: MonitorConfig,
        provider: SystemMetricsProvider | None = None,
        mqtt_client: MonitorMqttClient | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ):
        self.config = config
        self.provider = provider or SystemMetricsProvider(
            disk_path=config.disk_path,
            wifi_interface=config.wifi_interface,
        )
        self.mqtt = mqtt_client or MonitorMqttClient(
            config.mqtt_broker,
            config.mqtt_port,
        )
        self.monotonic_fn = monotonic_fn
        self._stop_event = threading.Event()
        self._status_lock = threading.RLock()
        self._snapshot = empty_snapshot(config.disk_path)
        self._emotion: str | None = None
        self._next_sample_at: float | None = None
        self._next_reassert_at: float | None = None

    def request_stop(self) -> None:
        self._stop_event.set()

    def stop(self) -> None:
        self.request_stop()
        self.mqtt.stop()

    def _tick(self, now: float) -> None:
        if self._next_sample_at is None or now >= self._next_sample_at:
            snapshot = self.provider.sample()
            metrics = snapshot.as_dict()["metrics"]
            emotion = select_emotion(
                metrics["cpu"]["percent"] if metrics["cpu"]["available"] else None,
                metrics["temperature"]["celsius"]
                if metrics["temperature"]["available"]
                else None,
                metrics["disk"]["free_bytes"] if metrics["disk"]["available"] else None,
            )
            with self._status_lock:
                self._snapshot = snapshot
                previous_emotion = self._emotion
                self._emotion = emotion

            if emotion != previous_emotion:
                if emotion is None:
                    self.mqtt.clear_emotion()
                    self._next_reassert_at = None
                else:
                    self.mqtt.set_emotion(emotion)
                    self._next_reassert_at = (
                        now + self.config.emotion_reassert_interval_seconds
                    )
            self._next_sample_at = now + self.config.sample_interval_seconds

        if (
            self._emotion is not None
            and self._next_reassert_at is not None
            and now >= self._next_reassert_at
        ):
            self.mqtt.set_emotion(self._emotion)
            self._next_reassert_at = (
                now + self.config.emotion_reassert_interval_seconds
            )

    def run(self) -> None:
        self.mqtt.connect()
        while not self._stop_event.is_set():
            now = self.monotonic_fn()
            self._tick(now)
            deadlines = [self._next_sample_at]
            if self._next_reassert_at is not None:
                deadlines.append(self._next_reassert_at)
            next_deadline = min(deadline for deadline in deadlines if deadline is not None)
            self._stop_event.wait(max(0.0, next_deadline - self.monotonic_fn()))

    def status(self) -> dict:
        with self._status_lock:
            snapshot = self._snapshot
            emotion = self._emotion
        payload = snapshot.as_dict()
        metrics = payload["metrics"]
        healthy = all(
            metrics[name]["available"] for name in ("cpu", "temperature", "disk")
        )
        return {
            "healthy": healthy,
            "status": "healthy" if healthy else "degraded",
            "emotion": emotion,
            "last_sample_time": snapshot.sampled_at or None,
            "metrics": metrics,
        }

    def health(self) -> dict[str, str]:
        status = self.status()
        return {"status": status["status"]}


def install_signal_handlers(service: MonitorService) -> None:
    import signal

    signal.signal(signal.SIGTERM, lambda signum, frame: service.request_stop())
    signal.signal(signal.SIGINT, lambda signum, frame: service.request_stop())
