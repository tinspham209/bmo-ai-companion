from queue import Queue
from threading import Event
from types import SimpleNamespace

import main


class FakeRuntime:
    def __init__(self, **kwargs):
        self.event_queue = Queue()
        self.events = []

    def set_publisher(self, publish_fn):
        self.events.append("publisher")

    def current_state(self):
        return SimpleNamespace(value="idle")

    def run(self):
        self.events.append("run")

    def stop(self):
        self.events.append("stop")


class FakeMqtt:
    def __init__(self, broker, port, event_queue):
        self.events = []

    def connect(self):
        self.events.append("connect")

    def publish(self, topic, payload):
        self.events.append(("publish", topic, payload))

    def stop(self):
        self.events.append("stop")


class FakeServer:
    def __init__(self):
        self.stopped = Event()
        self.closed = False

    def serve_forever(self):
        self.stopped.wait()

    def shutdown(self):
        self.stopped.set()

    def server_close(self):
        self.closed = True


def test_main_stops_api_and_mqtt_during_shutdown(monkeypatch):
    config = SimpleNamespace(
        fps_target=30,
        fps_fallback=24,
        sleep_timeout_seconds=300,
        fullscreen=True,
        resolution="auto",
        mqtt_broker="localhost",
        mqtt_port=1883,
        api_port=5200,
    )
    runtime = FakeRuntime()
    mqtt = FakeMqtt("localhost", 1883, runtime.event_queue)
    server = FakeServer()

    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(main, "FaceRuntime", lambda **kwargs: runtime)
    monkeypatch.setattr(main, "install_signal_handlers", lambda runtime: None)
    monkeypatch.setattr(main, "FaceMqttClient", lambda broker, port, queue: mqtt)
    monkeypatch.setattr(main, "make_server", lambda host, port, app, threaded: server)

    main.main()

    assert "stop" in runtime.events
    assert mqtt.events == ["connect", "stop"]
    assert server.stopped.is_set()
    assert server.closed
