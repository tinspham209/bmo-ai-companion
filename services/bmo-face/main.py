"""Entry point for bmo-face service."""

from __future__ import annotations

import threading

from api import create_app
from config import load_config
from mqtt_client import FaceMqttClient
from renderer import FaceRuntime, install_signal_handlers


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
    mqtt.connect()
    runtime.set_publisher(mqtt.publish)

    app = create_app(runtime.event_queue, runtime.current_state)
    api_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=cfg.api_port, debug=False, use_reloader=False),
        daemon=True,
    )
    api_thread.start()

    try:
        runtime.run()
    finally:
        mqtt.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
