import main as monitor_main
from config import MonitorConfig


class FakeService:
    def __init__(self, config):
        self.config = config
        self.stopped = False

    def status(self):
        return {"status": "degraded"}

    def run(self):
        return

    def stop(self):
        self.stopped = True


class FakeServer:
    def __init__(self):
        self.shutdown_called = False
        self.close_called = False

    def serve_forever(self):
        return

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.close_called = True


def test_main_binds_loopback_and_closes_api_and_service(monkeypatch):
    service = FakeService(MonitorConfig())
    server = FakeServer()
    bound = {}

    monkeypatch.setattr(monitor_main, "load_config", lambda: service.config)
    monkeypatch.setattr(monitor_main, "MonitorService", lambda config: service)
    monkeypatch.setattr(monitor_main, "install_signal_handlers", lambda instance: None)

    def make_server(host, port, app, threaded):
        bound.update(host=host, port=port, threaded=threaded)
        assert app.test_client().get("/health").status_code == 200
        return server

    monkeypatch.setattr(monitor_main, "make_server", make_server)

    monitor_main.main()

    assert bound == {"host": "127.0.0.1", "port": 5202, "threaded": True}
    assert service.stopped
    assert server.shutdown_called
    assert server.close_called
