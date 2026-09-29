from queue import Queue
import socket
from threading import Event

import paho.mqtt.client as mqtt
import pytest

from mqtt_client import FaceMqttClient


def _broker_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 1883), timeout=0.3):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _broker_available(), reason="local Mosquitto is not available")
def test_face_subscriber_consumes_retained_system_emotion():
    publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    connected = Event()
    publisher.on_connect = lambda client, userdata, flags, reason_code, properties=None: (
        connected.set() if not reason_code.is_failure else None
    )
    face_events = Queue()
    face = FaceMqttClient("localhost", 1883, face_events)
    try:
        publisher.connect("127.0.0.1", 1883, keepalive=10)
        publisher.loop_start()
        assert connected.wait(3.0)
        info = publisher.publish(
            "bmo/system/state",
            '{"emotion":"stressed"}',
            qos=1,
            retain=True,
        )
        info.wait_for_publish(timeout=3.0)

        face.connect()
        assert face_events.get(timeout=3.0) == {
            "name": "bmo/system/state",
            "payload": {"emotion": "stressed"},
        }
    finally:
        face.stop()
        cleared = publisher.publish(
            "bmo/system/state",
            b"",
            qos=1,
            retain=True,
        )
        cleared.wait_for_publish(timeout=3.0)
        publisher.disconnect()
        publisher.loop_stop()
