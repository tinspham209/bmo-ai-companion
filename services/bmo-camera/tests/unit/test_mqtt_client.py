import json
from queue import Queue
from types import SimpleNamespace

import mqtt_client
from mqtt_client import CameraMqttClient, FACE_STATE_TOPIC, PUBLISH_TOPICS


class FakeClient:
    def __init__(self, callback_version):
        self.calls = []
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

    def reconnect_delay_set(self, min_delay, max_delay):
        self.calls.append(("reconnect_delay_set", min_delay, max_delay))

    def connect_async(self, broker, port, keepalive):
        self.calls.append(("connect_async", broker, port, keepalive))

    def loop_start(self):
        self.calls.append(("loop_start",))

    def loop_stop(self):
        self.calls.append(("loop_stop",))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def subscribe(self, topic, qos):
        self.calls.append(("subscribe", topic, qos))

    def publish(self, topic, payload, qos):
        self.calls.append(("publish", topic, payload, qos))
        return SimpleNamespace(rc=0)


def install_fake_paho(monkeypatch):
    monkeypatch.setattr(
        mqtt_client,
        "mqtt",
        SimpleNamespace(
            Client=FakeClient,
            CallbackAPIVersion=SimpleNamespace(VERSION2="v2"),
            MQTT_ERR_SUCCESS=0,
        ),
    )


def test_connect_configures_reconnect_and_subscribes_to_face_state(monkeypatch):
    install_fake_paho(monkeypatch)
    states = Queue()
    adapter = CameraMqttClient("localhost", 1883, states)
    adapter.connect()

    assert ("reconnect_delay_set", 1, 30) in adapter.client.calls
    assert ("connect_async", "localhost", 1883, 30) in adapter.client.calls
    adapter.client.on_connect(adapter.client, None, {}, 0, None)
    assert ("subscribe", FACE_STATE_TOPIC, 1) in adapter.client.calls


def test_face_state_messages_are_validated_and_queued(caplog, monkeypatch):
    install_fake_paho(monkeypatch)
    states = Queue()
    adapter = CameraMqttClient("localhost", 1883, states)

    adapter.client.on_message(None, None, SimpleNamespace(
        topic=FACE_STATE_TOPIC,
        payload=b'{"state":"SLEEP"}',
    ))
    assert states.get_nowait() == "sleep"

    adapter.client.on_message(None, None, SimpleNamespace(topic=FACE_STATE_TOPIC, payload=b"{"))
    adapter.client.on_message(None, None, SimpleNamespace(
        topic=FACE_STATE_TOPIC,
        payload=b'{"state":"not-a-face-state"}',
    ))
    assert states.empty()
    assert "invalid JSON" in caplog.text
    assert "invalid face-state" in caplog.text


def test_camera_events_publish_minimal_json_contract(monkeypatch):
    install_fake_paho(monkeypatch)
    adapter = CameraMqttClient("localhost", 1883, Queue())
    adapter.client.on_connect(adapter.client, None, {}, 0, None)

    assert adapter.publish_event("person_detected", {})
    assert ("bmo/camera/person_detected", json.dumps({}), 1) in [
        call[1:] for call in adapter.client.calls if call[0] == "publish"
    ]
    assert set(PUBLISH_TOPICS) == {
        "person_detected",
        "person_left",
        "face_position",
        "motion",
        "no_motion",
    }


def test_events_queue_while_disconnected_and_flush_after_reconnect(monkeypatch):
    install_fake_paho(monkeypatch)
    adapter = CameraMqttClient("localhost", 1883, Queue())
    assert adapter.publish_event("person_left", {})
    assert not any(call[0] == "publish" for call in adapter.client.calls)

    adapter.client.on_connect(adapter.client, None, {}, 0, None)
    assert any(
        call[0] == "publish" and call[1] == "bmo/camera/person_left"
        for call in adapter.client.calls
    )


def test_unknown_event_name_fails_explicitly(monkeypatch):
    install_fake_paho(monkeypatch)
    adapter = CameraMqttClient("localhost", 1883, Queue())
    try:
        adapter.publish_event("frame", {})
    except ValueError as error:
        assert "unknown camera event" in str(error)
    else:
        raise AssertionError("unknown event should fail explicitly")
