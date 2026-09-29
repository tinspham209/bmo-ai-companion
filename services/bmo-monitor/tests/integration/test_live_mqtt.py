from threading import Event
import socket

import paho.mqtt.client as mqtt
import pytest

from mqtt_client import MonitorMqttClient, SYSTEM_STATE_TOPIC


def _broker_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 1883), timeout=0.3):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _broker_available(), reason="local Mosquitto is not available")
def test_retained_current_emotion_reaches_a_late_subscriber():
    publisher = MonitorMqttClient("localhost", 1883)
    subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    received = Event()
    tombstone_received = Event()
    messages = []
    verifier = None
    publisher_stopped = False

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if not getattr(reason_code, "is_failure", False):
            client.subscribe(SYSTEM_STATE_TOPIC, qos=1)

    def on_message(client, userdata, message):
        messages.append(message)
        received.set()
        if not message.payload:
            tombstone_received.set()

    subscriber.on_connect = on_connect
    subscriber.on_message = on_message
    try:
        publisher.connect()
        assert publisher.wait_connected(3.0)
        publisher.set_emotion("stressed")

        subscriber.connect("127.0.0.1", 1883, keepalive=10)
        subscriber.loop_start()
        assert received.wait(3.0)
        assert messages[0].topic == SYSTEM_STATE_TOPIC
        assert messages[0].payload == b'{"emotion": "stressed"}'
        assert messages[0].retain is True
        publisher.stop()
        publisher_stopped = True
        assert tombstone_received.wait(3.0)

        no_stale_state = Event()
        verifier = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        def verify_connect(client, userdata, flags, reason_code, properties=None):
            if not getattr(reason_code, "is_failure", False):
                client.subscribe(SYSTEM_STATE_TOPIC, qos=1)

        verifier.on_connect = verify_connect
        verifier.on_message = lambda *args: no_stale_state.set()
        verifier.connect("127.0.0.1", 1883, keepalive=10)
        verifier.loop_start()
        assert not no_stale_state.wait(0.5)
    finally:
        subscriber.disconnect()
        subscriber.loop_stop()
        if verifier is not None:
            verifier.disconnect()
            verifier.loop_stop()
        if not publisher_stopped:
            publisher.stop()
