"""Local health and status API for bmo-camera."""

from __future__ import annotations

from typing import Any, Callable

from flask import Flask, jsonify


def create_app(status_getter: Callable[[], dict[str, Any]]) -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        status = status_getter()
        healthy = bool(status.get("healthy"))
        return jsonify({"status": "ok" if healthy else "unhealthy"}), 200 if healthy else 503

    @app.get("/status")
    def get_status():
        return jsonify(status_getter())

    return app
