import json
from types import SimpleNamespace
from queue import Queue

import mqtt_client
from mqtt_client import FaceMqttClient, SUB_TOPICS


class FakeClient:
    def __init__(self, callback_api_version):
        self.callback_api_version = callback_api_version
        self.calls = []
        self.on_connect = None
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

    def subscribe(self, topic):
        self.calls.append(("subscribe", topic))

    def publish(self, topic, payload):
        self.calls.append(("publish", topic, payload))


def _fake_paho():
    return SimpleNamespace(
        Client=FakeClient,
        CallbackAPIVersion=SimpleNamespace(VERSION2=object()),
    )


def test_mqtt_client_subscribes_and_configures_reconnect(monkeypatch):
    monkeypatch.setattr(mqtt_client, "mqtt", _fake_paho())
    event_queue = Queue()
    adapter = FaceMqttClient("localhost", 1883, event_queue)

    assert ("reconnect_delay_set", 1, 30) in adapter.client.calls
    adapter.connect()
    assert ("connect_async", "localhost", 1883, 30) in adapter.client.calls
    adapter.client.on_connect(adapter.client, None, {}, 0)
    subscribed = [call[1] for call in adapter.client.calls if call[0] == "subscribe"]
    assert subscribed == SUB_TOPICS
    assert "bmo/voice/listening_start" in subscribed
    assert "bmo/face/brightness" in subscribed


def test_mqtt_client_accepts_only_json_objects(caplog, monkeypatch):
    monkeypatch.setattr(mqtt_client, "mqtt", _fake_paho())
    event_queue = Queue()
    adapter = FaceMqttClient("localhost", 1883, event_queue)

    adapter.client.on_message(None, None, SimpleNamespace(topic="bmo/system/state", payload=b'{"emotion":"happy"}'))
    assert event_queue.get_nowait() == {
        "name": "bmo/system/state",
        "payload": {"emotion": "happy"},
    }

    adapter.client.on_message(None, None, SimpleNamespace(topic="bmo/system/state", payload=b"{"))
    adapter.client.on_message(None, None, SimpleNamespace(topic="bmo/system/state", payload=b"[]"))
    adapter.client.on_message(None, None, SimpleNamespace(topic="bmo/face/brightness", payload=b'{"level":2}'))
    adapter.client.on_message(None, None, SimpleNamespace(topic="bmo/notify/event", payload=b'{"priority":[]}'))
    assert event_queue.empty()
    assert "invalid JSON" in caplog.text
    assert "non-object" in caplog.text
    assert "invalid payload" in caplog.text


def test_mqtt_client_ignores_retained_state_tombstone(monkeypatch):
    monkeypatch.setattr(mqtt_client, "mqtt", _fake_paho())
    event_queue = Queue()
    adapter = FaceMqttClient("localhost", 1883, event_queue)

    adapter.client.on_message(
        None,
        None,
        SimpleNamespace(topic="bmo/system/state", payload=b""),
    )

    assert event_queue.empty()


def test_mqtt_publish_serializes_json(monkeypatch):
    monkeypatch.setattr(mqtt_client, "mqtt", _fake_paho())
    adapter = FaceMqttClient("localhost", 1883, Queue())
    adapter.publish("bmo/face/state", {"state": "idle"})
    assert ("publish", "bmo/face/state", json.dumps({"state": "idle"})) in adapter.client.calls


def test_mqtt_stop_disconnects_before_stopping_loop(monkeypatch):
    monkeypatch.setattr(mqtt_client, "mqtt", _fake_paho())
    adapter = FaceMqttClient("localhost", 1883, Queue())
    adapter.stop()
    assert adapter.client.calls[-2:] == [("disconnect",), ("loop_stop",)]
