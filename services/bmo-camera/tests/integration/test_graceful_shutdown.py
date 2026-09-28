from threading import Event
from types import SimpleNamespace

import main


class FakeService:
    def __init__(self, config):
        self.stopped = False

    def status(self):
        return {"healthy": True}

    def run(self):
        return

    def stop(self):
        self.stopped = True


class FakeServer:
    def __init__(self):
        self._stop = Event()
        self.closed = False

    def serve_forever(self):
        self._stop.wait()

    def shutdown(self):
        self._stop.set()

    def server_close(self):
        self.closed = True


def test_main_closes_api_and_camera_service(monkeypatch):
    config = SimpleNamespace(api_port=5201)
    service = FakeService(config)
    server = FakeServer()

    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(main, "CameraService", lambda config: service)
    monkeypatch.setattr(main, "install_signal_handlers", lambda service: None)
    monkeypatch.setattr(main, "make_server", lambda host, port, app, threaded: server)

    main.main()

    assert service.stopped
    assert server.closed
    assert server._stop.is_set()
