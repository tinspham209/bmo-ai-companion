"""REST API for bmo-face."""

from __future__ import annotations

from queue import Queue

from flask import Flask, jsonify, request

from face.state_machine import FaceState


def create_app(event_queue: Queue, state_getter: callable):
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/state")
    def get_state():
        return jsonify({"state": state_getter().value})

    @app.post("/state")
    def set_state():
        data = request.get_json(silent=True) or {}
        name = str(data.get("state", "")).lower()
        if name not in {s.value for s in FaceState}:
            return jsonify({"error": "invalid state"}), 400
        event_queue.put({"name": "bmo/face/set_state", "payload": {"state": name}})
        return jsonify({"accepted": True, "state": name})

    @app.post("/brightness")
    def brightness():
        data = request.get_json(silent=True) or {}
        level = data.get("level")
        if not isinstance(level, (int, float)):
            return jsonify({"error": "level must be number"}), 400
        if not (0.0 <= float(level) <= 1.0):
            return jsonify({"error": "level must be between 0.0 and 1.0"}), 400
        event_queue.put({"name": "bmo/face/brightness", "payload": {"level": float(level)}})
        return jsonify({"accepted": True, "level": float(level)})

    return app

