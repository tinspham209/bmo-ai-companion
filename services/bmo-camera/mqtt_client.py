"""MQTT transport for camera events and face-state synchronization."""

from __future__ import annotations

from collections import deque
import json
import logging
from queue import Full, Queue
from threading import Event, Lock
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - dependency error is raised by constructor
    mqtt = None

logger = logging.getLogger(__name__)

FACE_STATE_TOPIC = "bmo/face/state"
PUBLISH_TOPICS = {
    "person_detected": "bmo/camera/person_detected",
    "person_left": "bmo/camera/person_left",
    "face_position": "bmo/camera/face_position",
    "motion": "bmo/camera/motion",
    "no_motion": "bmo/camera/no_motion",
}
FACE_STATES = {
    "boot", "idle", "look_left", "look_right", "sleep", "wake", "happy",
    "thinking", "listening", "speaking", "sad", "stressed", "hot", "worried",
    "alert",
}


class CameraMqttClient:
    def __init__(
        self,
        broker: str,
        port: int,
        face_state_queue: Queue[str],
        pending_limit: int = 256,
    ):
        if mqtt is None:
            raise RuntimeError("paho-mqtt is required")
        self.broker = broker
        self.port = port
        self.face_state_queue = face_state_queue
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._connected = False
        self._connected_event = Event()
        self._lock = Lock()
        self._pending: deque[tuple[str, dict[str, Any]]] = deque()
        if pending_limit < 1:
            raise ValueError("pending_limit must be > 0")
        self._pending_limit = pending_limit

    def connect(self) -> None:
        self.client.connect_async(self.broker, self.port, keepalive=30)
        self.client.loop_start()

    def wait_connected(self, timeout: float) -> bool:
        return self._connected_event.wait(timeout)

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        with self._lock:
            if not self._connected:
                return self._queue_locked(topic, payload)
            info = self.client.publish(topic, json.dumps(payload), qos=1)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            logger.warning("MQTT publish failed for %s (rc=%s); queueing event", topic, info.rc)
            return self._queue_locked(topic, payload)

    def publish_event(self, event_name: str, payload: dict[str, Any]) -> bool:
        topic = PUBLISH_TOPICS.get(event_name)
        if topic is None:
            raise ValueError(f"unknown camera event: {event_name}")
        return self.publish(topic, payload)

    def _queue_locked(self, topic: str, payload: dict[str, Any]) -> bool:
        if len(self._pending) >= self._pending_limit:
            logger.error("Camera MQTT pending queue is full; dropping event for %s", topic)
            return False
        self._pending.append((topic, dict(payload)))
        return True

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if self._reason_failed(reason_code):
            logger.error("MQTT connection failed: %s", reason_code)
            return
        with self._lock:
            self._connected = True
            client.subscribe(FACE_STATE_TOPIC, qos=1)
            self._connected_event.set()
            while self._pending:
                topic, payload = self._pending[0]
                info = client.publish(topic, json.dumps(payload), qos=1)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    self._connected = False
                    logger.warning("MQTT reconnect flush failed for %s (rc=%s)", topic, info.rc)
                    break
                self._pending.popleft()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        with self._lock:
            self._connected = False
            self._connected_event.clear()
        if self._reason_failed(reason_code):
            logger.warning("MQTT disconnected: %s", reason_code)

    @staticmethod
    def _reason_failed(reason_code) -> bool:
        failure = getattr(reason_code, "is_failure", None)
        if failure is not None:
            return bool(failure)
        try:
            return int(reason_code) != 0
        except (TypeError, ValueError):
            return True

    def _on_message(self, client, userdata, message) -> None:
        if message.topic != FACE_STATE_TOPIC:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8")) if message.payload else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Ignoring invalid JSON on MQTT topic %s", message.topic)
            return
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("state"), str)
            or payload["state"].lower() not in FACE_STATES
        ):
            logger.warning("Ignoring invalid face-state payload")
            return
        self.face_state_queue.put(payload["state"].lower())

    def stop(self) -> None:
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
