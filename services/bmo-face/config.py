"""Configuration loader for bmo-face."""

from __future__ import annotations

import re
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
        if self.fps_fallback >= self.fps_target:
            raise ValueError("face.fps_fallback must be < face.fps_target")
        if self.sleep_timeout_seconds <= 0:
            raise ValueError("face.sleep_timeout_seconds must be > 0")
        if not self.mqtt_broker.strip():
            raise ValueError("face.mqtt_broker must not be empty")
        if not 1 <= self.mqtt_port <= 65535:
            raise ValueError("face.mqtt_port must be between 1 and 65535")
        if not 1 <= self.api_port <= 65535:
            raise ValueError("face.api_port must be between 1 and 65535")
        if self.resolution != "auto" and not re.fullmatch(r"\d+x\d+", self.resolution):
            raise ValueError('face.resolution must be "auto" or WIDTHxHEIGHT')
        if self.resolution != "auto":
            width, height = (int(value) for value in self.resolution.split("x"))
            if width <= 0 or height <= 0:
                raise ValueError("face.resolution dimensions must be > 0")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a mapping")
    return data


def load_config(path: str | Path | None = None) -> FaceConfig:
    config_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "config" / "bmo.yaml"
    raw = _read_yaml(config_path)
    face = raw.get("face", {})
    if not isinstance(face, dict):
        raise ValueError("face configuration must be a mapping")

    def read_int(name: str, default: int) -> int:
        value = face.get(name, default)
        if isinstance(value, bool):
            raise ValueError(f"face.{name} must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError as error:
                raise ValueError(f"face.{name} must be an integer") from error
        raise ValueError(f"face.{name} must be an integer")

    fullscreen = face.get("fullscreen", True)
    if not isinstance(fullscreen, bool):
        raise ValueError("face.fullscreen must be a boolean")

    cfg = FaceConfig(
        fps_target=read_int("fps_target", 30),
        fps_fallback=read_int("fps_fallback", 24),
        fullscreen=fullscreen,
        resolution=str(face.get("resolution", "auto")),
        sleep_timeout_seconds=read_int("sleep_timeout_seconds", 300),
        mqtt_broker=str(face.get("mqtt_broker", "localhost")),
        mqtt_port=read_int("mqtt_port", 1883),
        api_port=read_int("api_port", 5200),
    )
    cfg.validate()
    return cfg
