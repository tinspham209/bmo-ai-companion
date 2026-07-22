"""MQTT transport adapter for bmo-face."""

from __future__ import annotations

import json
from queue import Queue
from typing import Any

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover
    mqtt = None


SUB_TOPICS = [
    "bmo/camera/person_detected",
    "bmo/camera/person_left",
    "bmo/camera/face_position",
    "bmo/voice/wake_word",
    "bmo/ai/speaking_start",
    "bmo/ai/speaking_end",
    "bmo/system/state",
    "bmo/ai/proactive_start",
    "bmo/notify/event",
    "bmo/voice/bt_disconnect",
    "bmo/face/set_state",
]


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
        except json.JSONDecodeError:
            payload = {}
        self.event_queue.put({"name": msg.topic, "payload": payload})

    def connect(self) -> None:  # pragma: no cover
        # Non-blocking connect so service can boot even if broker is temporarily down.
        self.client.connect_async(self.broker, self.port, keepalive=30)
        self.client.loop_start()

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.client.publish(topic, json.dumps(payload))

    def stop(self) -> None:  # pragma: no cover
        self.client.loop_stop()
        self.client.disconnect()
