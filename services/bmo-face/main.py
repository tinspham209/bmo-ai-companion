"""Entry point for bmo-face service."""

from __future__ import annotations

import threading

from api import create_app
from config import load_config
from mqtt_client import FaceMqttClient
from renderer import FaceRuntime, install_signal_handlers
from werkzeug.serving import make_server


def main():  # pragma: no cover
    cfg = load_config()
    runtime = FaceRuntime(
        fps_target=cfg.fps_target,
        fps_fallback=cfg.fps_fallback,
        sleep_timeout_seconds=cfg.sleep_timeout_seconds,
        fullscreen=cfg.fullscreen,
        resolution=cfg.resolution,
    )
    install_signal_handlers(runtime)
    mqtt = FaceMqttClient(cfg.mqtt_broker, cfg.mqtt_port, runtime.event_queue)
    mqtt = FaceMqttClient(cfg.mqtt_broker, cfg.mqtt_port, runtime.event_queue)
    api_server = None
    api_thread = None
    api_thread_started = False
    try:
        mqtt.connect()
        runtime.set_publisher(mqtt.publish)
        app = create_app(runtime.event_queue, runtime.current_state)
        api_server = make_server("127.0.0.1", cfg.api_port, app, threaded=True)
        api_thread = threading.Thread(target=api_server.serve_forever, name="bmo-face-api")
        api_thread.start()
        api_thread_started = True
        runtime.run()
    finally:
        runtime.stop()
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
                mqtt.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
