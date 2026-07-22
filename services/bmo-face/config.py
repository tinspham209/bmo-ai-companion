"""Configuration loader for bmo-face."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FaceConfig:
    fps_target: int = 30
    fps_fallback: int = 24
    fullscreen: bool = True
    resolution: str = "auto"
    sleep_timeout_seconds: int = 300
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    api_port: int = 5200

    def validate(self) -> None:
        if self.fps_target <= 0:
            raise ValueError("face.fps_target must be > 0")
        if self.fps_fallback <= 0:
            raise ValueError("face.fps_fallback must be > 0")
        if self.fps_fallback > self.fps_target:
            raise ValueError("face.fps_fallback must be <= face.fps_target")
        if self.sleep_timeout_seconds <= 0:
            raise ValueError("face.sleep_timeout_seconds must be > 0")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str | Path = "config/bmo.yaml") -> FaceConfig:
    raw = _read_yaml(Path(path))
    face = raw.get("face", {})
    cfg = FaceConfig(
        fps_target=int(face.get("fps_target", 30)),
        fps_fallback=int(face.get("fps_fallback", 24)),
        fullscreen=bool(face.get("fullscreen", True)),
        resolution=str(face.get("resolution", "auto")),
        sleep_timeout_seconds=int(face.get("sleep_timeout_seconds", 300)),
        mqtt_broker=str(face.get("mqtt_broker", "localhost")),
        mqtt_port=int(face.get("mqtt_port", 1883)),
        api_port=int(face.get("api_port", 5200)),
    )
    cfg.validate()
    return cfg

