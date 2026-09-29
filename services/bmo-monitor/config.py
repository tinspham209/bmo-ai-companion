"""Configuration loader and validation for bmo-monitor."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MonitorConfig:
    sample_interval_seconds: float = 5.0
    emotion_reassert_interval_seconds: float = 2.0
    cpu_stress_percent: float = 80.0
    temperature_hot_c: float = 70.0
    disk_worried_free_bytes: int = 500_000_000
    disk_path: str = "/"
    api_port: int = 5202
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    wifi_interface: str = "auto"

    def validate(self) -> None:
        if not 0.0 < self.sample_interval_seconds <= 300.0:
            raise ValueError("monitor.sample_interval_seconds must be in (0, 300]")
        if not 0.0 < self.emotion_reassert_interval_seconds <= 2.0:
            raise ValueError("monitor.emotion_reassert_interval_seconds must be in (0, 2]")
        if self.cpu_stress_percent != 80.0:
            raise ValueError("monitor.cpu_stress_percent must be 80")
        if self.temperature_hot_c != 70.0:
            raise ValueError("monitor.temperature_hot_c must be 70")
        if self.disk_worried_free_bytes != 500_000_000:
            raise ValueError("monitor.disk_worried_free_bytes must be 500000000")
        if not Path(self.disk_path).is_absolute():
            raise ValueError("monitor.disk_path must be an absolute path")
        if not 1 <= self.api_port <= 65535:
            raise ValueError("monitor.api_port must be between 1 and 65535")
        if not MonitorConfig._is_loopback_host(self.mqtt_broker):
            raise ValueError("monitor.mqtt_broker must be localhost or a loopback IP")
        if not 1 <= self.mqtt_port <= 65535:
            raise ValueError("monitor.mqtt_port must be between 1 and 65535")
        if self.wifi_interface != "auto" and (
            not self.wifi_interface
            or len(self.wifi_interface) > 15
            or not all(character.isalnum() or character in "_.:-" for character in self.wifi_interface)
        ):
            raise ValueError("monitor.wifi_interface must be auto or a valid interface name")

    @staticmethod
    def _is_loopback_host(host: str) -> bool:
        if host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False


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


def _read_number(section: dict[str, Any], name: str, default: int | float) -> int | float:
    value = section.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"monitor.{name} must be a number")
    return value


def _read_int(section: dict[str, Any], name: str, default: int) -> int:
    value = section.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"monitor.{name} must be an integer")
    return value


def load_config(path: str | Path | None = None) -> MonitorConfig:
    config_path = (
        Path(path)
        if path is not None
        else Path(__file__).resolve().parents[2] / "config" / "bmo.yaml"
    )
    raw = _read_yaml(config_path)
    monitor = raw.get("monitor", {})
    if not isinstance(monitor, dict):
        raise ValueError("monitor configuration must be a mapping")

    mqtt_broker = monitor.get("mqtt_broker", "localhost")
    disk_path = monitor.get("disk_path", "/")
    wifi_interface = monitor.get("wifi_interface", "auto")
    if not isinstance(mqtt_broker, str):
        raise ValueError("monitor.mqtt_broker must be a string")
    if not isinstance(disk_path, str):
        raise ValueError("monitor.disk_path must be a string")
    if not isinstance(wifi_interface, str):
        raise ValueError("monitor.wifi_interface must be a string")

    config = MonitorConfig(
        sample_interval_seconds=float(_read_number(monitor, "sample_interval_seconds", 5.0)),
        emotion_reassert_interval_seconds=float(
            _read_number(monitor, "emotion_reassert_interval_seconds", 2.0)
        ),
        cpu_stress_percent=float(_read_number(monitor, "cpu_stress_percent", 80.0)),
        temperature_hot_c=float(_read_number(monitor, "temperature_hot_c", 70.0)),
        disk_worried_free_bytes=_read_int(
            monitor, "disk_worried_free_bytes", 500_000_000
        ),
        disk_path=disk_path,
        api_port=_read_int(monitor, "api_port", 5202),
        mqtt_broker=mqtt_broker,
        mqtt_port=_read_int(monitor, "mqtt_port", 1883),
        wifi_interface=wifi_interface,
    )
    config.validate()
    return config
