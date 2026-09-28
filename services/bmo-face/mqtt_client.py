"""MQTT transport adapter for bmo-face."""

from __future__ import annotations

import json
import logging
import math
from queue import Queue
from typing import Any

logger = logging.getLogger(__name__)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (isinstance(value, int) or math.isfinite(value))
    )


try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None


SUB_TOPICS = [
    "bmo/camera/person_detected",
    "bmo/camera/person_left",
    "bmo/camera/face_position",
    "bmo/voice/wake_word",
    "bmo/voice/listening_start",
    "bmo/ai/speaking_start",
    "bmo/ai/speaking_end",
    "bmo/system/state",
    "bmo/ai/proactive_start",
    "bmo/notify/event",
    "bmo/voice/bt_disconnect",
    "bmo/face/set_state",
    "bmo/face/brightness",
]


def _valid_payload(topic: str, payload: dict[str, Any]) -> bool:
    if topic == "bmo/face/set_state":
        return isinstance(payload.get("state"), str)
    if topic == "bmo/face/brightness":
        level = payload.get("level")
        return (
            _is_finite_number(level)
            and 0.0 <= level <= 1.0
        )
    if topic == "bmo/camera/face_position":
        x = payload.get("x")
        return (
            _is_finite_number(x)
            and 0.0 <= x <= 1.0
        )
    if topic == "bmo/system/state":
        emotion = payload.get("emotion")
        return isinstance(emotion, str) and emotion in {"happy", "stressed", "hot", "worried"}
    if topic == "bmo/notify/event":
        priority = payload.get("priority")
        return (
            isinstance(priority, str)
            and priority in {"low", "medium", "high"}
            and isinstance(payload.get("title", ""), str)
            and isinstance(payload.get("message", ""), str)
        )
    if topic == "bmo/ai/speaking_start":
        amplitude = payload.get("amplitude", [])
        rate = payload.get("sample_rate_hz", 10)
        return (
            isinstance(amplitude, list)
            and all(
                _is_finite_number(value)
                for value in amplitude
            )
            and isinstance(rate, int)
            and not isinstance(rate, bool)
            and 1 <= rate <= 1000
        )
    return True


class FaceMqttClient:
    def __init__(self, broker: str, port: int, event_queue: Queue):
        if mqtt is None:
            raise RuntimeError("paho-mqtt is required")
        self.broker = broker
        self.port = port
        self.event_queue = event_queue
        self.client = mqtt.Client()
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):  # pragma: no cover
        for topic in SUB_TOPICS:
            client.subscribe(topic)

    def _on_message(self, client, userdata, msg):  # pragma: no cover
        try:
            payload = json.loads(msg.payload.decode("utf-8")) if msg.payload else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Ignoring invalid JSON on MQTT topic %s", msg.topic)
            return
        if not isinstance(payload, dict):
            logger.warning("Ignoring non-object MQTT payload on topic %s", msg.topic)
            return
        if not _valid_payload(msg.topic, payload):
            logger.warning("Ignoring invalid payload on MQTT topic %s", msg.topic)
            return
        self.event_queue.put({"name": msg.topic, "payload": payload})

    def connect(self) -> None:  # pragma: no cover
        # Non-blocking connect so service can boot even if broker is temporarily down.
        self.client.connect_async(self.broker, self.port, keepalive=30)
        self.client.loop_start()

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.client.publish(topic, json.dumps(payload))

    def stop(self) -> None:  # pragma: no cover
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
