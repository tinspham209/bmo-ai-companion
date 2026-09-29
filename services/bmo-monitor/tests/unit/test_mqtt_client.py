import json
from types import SimpleNamespace

import pytest

import mqtt_client
from mqtt_client import MonitorMqttClient, SYSTEM_STATE_TOPIC


class FakeClient:
    def __init__(self, callback_api_version):
        self.calls = [("init", callback_api_version)]
        self.on_connect = None
        self.on_disconnect = None

    def reconnect_delay_set(self, min_delay, max_delay):
        self.calls.append(("reconnect_delay_set", min_delay, max_delay))

    def will_set(self, topic, payload, qos, retain):
        self.calls.append(("will_set", topic, payload, qos, retain))

    def connect_async(self, broker, port, keepalive):
        self.calls.append(("connect_async", broker, port, keepalive))

    def loop_start(self):
        self.calls.append(("loop_start",))

    def loop_stop(self):
        self.calls.append(("loop_stop",))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def publish(self, topic, payload, qos, retain):
        self.calls.append(("publish", topic, payload, qos, retain))
        return SimpleNamespace(rc=0, wait_for_publish=lambda timeout: None)


def _install_fake_paho(monkeypatch):
    api_version = object()
    fake_mqtt = SimpleNamespace(
        Client=FakeClient,
        CallbackAPIVersion=SimpleNamespace(VERSION2=api_version),
        MQTT_ERR_SUCCESS=0,
    )
    monkeypatch.setattr(mqtt_client, "mqtt", fake_mqtt)
    return api_version


def test_connection_configures_reconnect_and_clearing_will(monkeypatch):
    api_version = _install_fake_paho(monkeypatch)
    adapter = MonitorMqttClient("localhost", 1883)

    assert ("init", api_version) in adapter.client.calls
    assert ("reconnect_delay_set", 1, 30) in adapter.client.calls
    assert (
        "will_set",
        SYSTEM_STATE_TOPIC,
        b"",
        1,
        True,
    ) in adapter.client.calls

    adapter.connect()
    assert ("connect_async", "localhost", 1883, 30) in adapter.client.calls
    assert ("loop_start",) in adapter.client.calls


def test_state_is_retained_at_qos_one_and_republished_on_reconnect(monkeypatch):
    _install_fake_paho(monkeypatch)
    adapter = MonitorMqttClient("localhost", 1883)
    adapter.set_emotion("hot")
    assert not [call for call in adapter.client.calls if call[0] == "publish"]

    adapter.client.on_connect(adapter.client, None, {}, 0)
    publish_calls = [call for call in adapter.client.calls if call[0] == "publish"]
    assert publish_calls[-1] == (
        "publish",
        SYSTEM_STATE_TOPIC,
        json.dumps({"emotion": "hot"}),
        1,
        True,
    )

    adapter.client.on_disconnect(adapter.client, None, {}, 1)
    adapter.client.on_connect(adapter.client, None, {}, 0)
    publish_calls = [call for call in adapter.client.calls if call[0] == "publish"]
    assert len(publish_calls) == 2
    assert publish_calls[-1][2] == json.dumps({"emotion": "hot"})


def test_empty_retained_payload_clears_state(monkeypatch):
    _install_fake_paho(monkeypatch)
    adapter = MonitorMqttClient("localhost", 1883)
    adapter.client.on_connect(adapter.client, None, {}, 0)
    adapter.set_emotion("happy")
    adapter.clear_emotion()

    publish_calls = [call for call in adapter.client.calls if call[0] == "publish"]
    assert publish_calls[-1] == ("publish", SYSTEM_STATE_TOPIC, b"", 1, True)


def test_unsupported_emotion_is_rejected(monkeypatch):
    _install_fake_paho(monkeypatch)
    adapter = MonitorMqttClient("localhost", 1883)

    with pytest.raises(ValueError, match="unsupported"):
        adapter.set_emotion("unknown")


def test_stop_clears_retained_state_and_stops_client(monkeypatch):
    _install_fake_paho(monkeypatch)
    adapter = MonitorMqttClient("localhost", 1883)
    adapter.client.on_connect(adapter.client, None, {}, 0)
    adapter.set_emotion("happy")

    adapter.stop()

    assert adapter.client.calls[-2:] == [("disconnect",), ("loop_stop",)]
    assert [call for call in adapter.client.calls if call[0] == "publish"][-1][2] == b""
