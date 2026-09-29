"""Retained MQTT publisher for the current monitor emotion."""

from __future__ import annotations

import json
import logging
from threading import Event, Lock

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - dependency error is raised by constructor
    mqtt = None

logger = logging.getLogger(__name__)

SYSTEM_STATE_TOPIC = "bmo/system/state"
EMOTIONS = {"happy", "stressed", "hot", "worried"}


class MonitorMqttClient:
    def __init__(self, broker: str, port: int):
        if mqtt is None:
            raise RuntimeError("paho-mqtt is required")
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.will_set(SYSTEM_STATE_TOPIC, payload=b"", qos=1, retain=True)
        self._lock = Lock()
        self._connected = False
        self._connected_event = Event()
        self._emotion: str | None = None
        self.broker = broker
        self.port = port

    def connect(self) -> None:
        self.client.connect_async(self.broker, self.port, keepalive=30)
        self.client.loop_start()

    def wait_connected(self, timeout: float) -> bool:
        return self._connected_event.wait(timeout)

    def set_emotion(self, emotion: str) -> bool:
        if emotion not in EMOTIONS:
            raise ValueError(f"unsupported system emotion: {emotion}")
        with self._lock:
            self._emotion = emotion
            return self._publish_current_locked() if self._connected else True

    def clear_emotion(self) -> bool:
        with self._lock:
            self._emotion = None
            return self._publish_current_locked() if self._connected else True

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if self._reason_failed(reason_code):
            logger.error("MQTT connection failed: %s", reason_code)
            return
        with self._lock:
            self._connected = True
            self._connected_event.set()
            self._publish_current_locked()

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ) -> None:
        with self._lock:
            self._connected = False
            self._connected_event.clear()
        if self._reason_failed(reason_code):
            logger.warning("MQTT disconnected: %s", reason_code)

    def _publish_current_locked(self, wait: bool = False) -> bool:
        payload = (
            json.dumps({"emotion": self._emotion})
            if self._emotion is not None
            else b""
        )
        info = self.client.publish(
            SYSTEM_STATE_TOPIC,
            payload,
            qos=1,
            retain=True,
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning(
                "MQTT state publish failed for %s (rc=%s)",
                SYSTEM_STATE_TOPIC,
                info.rc,
            )
            return False
        if wait:
            try:
                info.wait_for_publish(timeout=1.0)
            except RuntimeError:
                logger.warning("Timed out clearing retained monitor state")
        return True

    @staticmethod
    def _reason_failed(reason_code) -> bool:
        failure = getattr(reason_code, "is_failure", None)
        if failure is not None:
            return bool(failure)
        try:
            return int(reason_code) != 0
        except (TypeError, ValueError):
            return True

    def stop(self) -> None:
        try:
            with self._lock:
                self._emotion = None
                if self._connected:
                    self._publish_current_locked(wait=True)
            self.client.disconnect()
        finally:
            self.client.loop_stop()
