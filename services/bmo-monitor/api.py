"""Local health and status API for bmo-monitor."""

from __future__ import annotations

from typing import Any, Callable

from flask import Flask, jsonify


def create_app(status_getter: Callable[[], dict[str, Any]]) -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": status_getter()["status"]}), 200

    @app.get("/status")
    def get_status():
        return jsonify(status_getter())

    return app
