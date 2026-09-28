"""REST API for bmo-face."""

from __future__ import annotations

from queue import Queue
from typing import Any, Callable

from flask import Flask, jsonify, request

from face.state_machine import FaceState


def create_app(event_queue: Queue, state_getter: Callable[[], FaceState]) -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/state")
    def get_state():
        return jsonify({"state": state_getter().value})

    @app.post("/state")
    def set_state():
        data: Any = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object required"}), 400
        name = str(data.get("state", "")).lower()
        if name not in {s.value for s in FaceState}:
            return jsonify({"error": "invalid state"}), 400
        event_queue.put({"name": "bmo/face/set_state", "payload": {"state": name}})
        return jsonify({"accepted": True, "state": name})

    @app.post("/brightness")
    def brightness():
        data: Any = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object required"}), 400
        level = data.get("level")
        if not isinstance(level, (int, float)) or isinstance(level, bool):
            return jsonify({"error": "level must be number"}), 400
        if not (0.0 <= float(level) <= 1.0):
            return jsonify({"error": "level must be between 0.0 and 1.0"}), 400
        event_queue.put({"name": "bmo/face/brightness", "payload": {"level": float(level)}})
        return jsonify({"accepted": True, "level": float(level)})

    return app
