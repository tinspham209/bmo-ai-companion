"""Entry point for the independent bmo-camera service."""

from __future__ import annotations

import threading

from api import create_app
from camera import CameraService, install_signal_handlers
from config import load_config
from werkzeug.serving import make_server


def main() -> None:
    config = load_config()
    service = CameraService(config)
    install_signal_handlers(service)

    api_server = None
    api_thread = None
    api_thread_started = False
    try:
        api_server = make_server(
            "127.0.0.1",
            config.api_port,
            create_app(service.status),
            threaded=True,
        )
        api_thread = threading.Thread(target=api_server.serve_forever, name="bmo-camera-api")
        api_thread.start()
        api_thread_started = True
        service.run()
    finally:
        service.stop()
        try:
            if api_server is not None:
                if api_thread_started:
                    api_server.shutdown()
                api_server.server_close()
        finally:
            try:
                if api_thread is not None and api_thread_started:
                    api_thread.join()
            finally:
                service.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
