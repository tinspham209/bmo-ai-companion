"""Configuration loader and validation for bmo-camera."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class CameraConfig:
    backend: str = "auto"
    device_index: int = 0
    active_fps: int | None = None
    sleep_fps: int = 5
    analysis_width: int = 320
    min_face_size: int = 24
    face_absent_seconds: int = 10
    face_position_max_hz: int = 5
    face_position_min_delta: float = 0.05
    face_position_heartbeat_seconds: float = 0.4
    motion_threshold_ratio: float = 0.02
    no_motion_timeout_seconds: int = 30
    face_state_url: str = "http://127.0.0.1:5200/state"
    face_state_timeout_seconds: float = 1.0
    api_port: int = 5201
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883

    def validate(self) -> None:
        if self.backend not in {"auto", "avfoundation", "v4l2"}:
            raise ValueError("camera.backend must be auto, avfoundation, or v4l2")
        if self.device_index < 0:
            raise ValueError("camera.device_index must be >= 0")
        if self.active_fps is not None and not 1 <= self.active_fps <= 120:
            raise ValueError("camera.active_fps must be auto or an integer from 1 to 120")
        if self.sleep_fps != 5:
            raise ValueError("camera.sleep_fps must be 5")
        if self.analysis_width < 64:
            raise ValueError("camera.analysis_width must be >= 64")
        if self.min_face_size < 1:
            raise ValueError("camera.min_face_size must be > 0")
        if self.face_absent_seconds != 10:
            raise ValueError("camera.face_absent_seconds must be 10")
        if self.face_position_max_hz < 1:
            raise ValueError("camera.face_position_max_hz must be > 0")
        if not 0.0 < self.face_position_min_delta <= 1.0:
            raise ValueError("camera.face_position_min_delta must be in (0, 1]")
        if not 0.0 < self.face_position_heartbeat_seconds <= 0.5:
            raise ValueError("camera.face_position_heartbeat_seconds must be in (0, 0.5]")
        if not 0.0 < self.motion_threshold_ratio <= 1.0:
            raise ValueError("camera.motion_threshold_ratio must be in (0, 1]")
        if self.no_motion_timeout_seconds <= 0:
            raise ValueError("camera.no_motion_timeout_seconds must be > 0")
        if not self._is_loopback_http_url(self.face_state_url):
            raise ValueError("camera.face_state_url must use localhost or a loopback IP")
        if not 0.0 < self.face_state_timeout_seconds <= 10.0:
            raise ValueError("camera.face_state_timeout_seconds must be in (0, 10]")
        if not 1 <= self.api_port <= 65535:
            raise ValueError("camera.api_port must be between 1 and 65535")
        if not self._is_loopback_host(self.mqtt_broker):
            raise ValueError("camera.mqtt_broker must be localhost or a loopback IP")
        if not 1 <= self.mqtt_port <= 65535:
            raise ValueError("camera.mqtt_port must be between 1 and 65535")

    @staticmethod
    def _is_loopback_host(host: str) -> bool:
        if host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _is_loopback_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return (
            parsed.scheme == "http"
            and parsed.hostname is not None
            and CameraConfig._is_loopback_host(parsed.hostname)
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("configuration root must be a mapping")
    return data


def load_config(path: str | Path | None = None) -> CameraConfig:
    config_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "config" / "bmo.yaml"
    raw = _read_yaml(config_path)
    camera = raw.get("camera", {})
    if not isinstance(camera, dict):
        raise ValueError("camera configuration must be a mapping")

    def read_int(name: str, default: int) -> int:
        value = camera.get(name, default)
        if isinstance(value, bool):
            raise ValueError(f"camera.{name} must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError as error:
                raise ValueError(f"camera.{name} must be an integer") from error
        raise ValueError(f"camera.{name} must be an integer")

    def read_float(name: str, default: float) -> float:
        value = camera.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"camera.{name} must be a number")
        return float(value)

    active_fps_value = camera.get("active_fps", "auto")
    if active_fps_value == "auto":
        active_fps = None
    elif isinstance(active_fps_value, int) and not isinstance(active_fps_value, bool):
        active_fps = active_fps_value
    else:
        raise ValueError("camera.active_fps must be auto or an integer")

    config = CameraConfig(
        backend=str(camera.get("backend", "auto")).lower(),
        device_index=read_int("device_index", 0),
        active_fps=active_fps,
        sleep_fps=read_int("sleep_fps", 5),
        analysis_width=read_int("analysis_width", 320),
        min_face_size=read_int("min_face_size", 24),
        face_absent_seconds=read_int("face_absent_seconds", 10),
        face_position_max_hz=read_int("face_position_max_hz", 5),
        face_position_min_delta=read_float("face_position_min_delta", 0.05),
        face_position_heartbeat_seconds=read_float("face_position_heartbeat_seconds", 0.4),
        motion_threshold_ratio=read_float("motion_threshold_ratio", 0.02),
        no_motion_timeout_seconds=read_int("no_motion_timeout_seconds", 30),
        face_state_url=str(camera.get("face_state_url", "http://127.0.0.1:5200/state")),
        face_state_timeout_seconds=read_float("face_state_timeout_seconds", 1.0),
        api_port=read_int("api_port", 5201),
        mqtt_broker=str(camera.get("mqtt_broker", "localhost")),
        mqtt_port=read_int("mqtt_port", 1883),
    )
    config.validate()
    return config
