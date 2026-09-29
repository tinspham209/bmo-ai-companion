"""Local system metric providers for bmo-monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable

import psutil


@dataclass(frozen=True)
class MetricStatus:
    available: bool
    values: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, str | int | float | bool | None]:
        result: dict[str, str | int | float | bool | None] = {
            "available": self.available,
            **self.values,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass(frozen=True)
class MetricsSnapshot:
    sampled_at: str
    cpu: MetricStatus
    ram: MetricStatus
    temperature: MetricStatus
    disk: MetricStatus
    wifi: MetricStatus
    bluetooth: MetricStatus

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_sample_time": self.sampled_at,
            "metrics": {
                "cpu": self.cpu.as_dict(),
                "ram": self.ram.as_dict(),
                "temperature": self.temperature.as_dict(),
                "disk": self.disk.as_dict(),
                "wifi": self.wifi.as_dict(),
                "bluetooth": self.bluetooth.as_dict(),
            },
        }


def cpu_percent_from_times(previous: Any, current: Any) -> float:
    """Calculate busy CPU percentage from two psutil cpu_times-style values."""
    counter_names = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")
    previous_values = [float(getattr(previous, name, 0.0)) for name in counter_names]
    current_values = [float(getattr(current, name, 0.0)) for name in counter_names]
    if any(not math.isfinite(value) or value < 0 for value in previous_values + current_values):
        raise ValueError("CPU counters must be finite and non-negative")

    deltas = [new - old for old, new in zip(previous_values, current_values, strict=True)]
    if any(delta < 0 for delta in deltas):
        raise ValueError("CPU counters decreased")
    total_delta = sum(deltas)
    if total_delta <= 0:
        raise ValueError("CPU counters did not advance")
    idle_delta = deltas[3] + deltas[4]
    if idle_delta > total_delta:
        raise ValueError("CPU idle time exceeds total time")
    return (total_delta - idle_delta) * 100.0 / total_delta


class SystemMetricsProvider:
    def __init__(
        self,
        disk_path: str = "/",
        wifi_interface: str = "auto",
        thermal_root: str | Path = "/sys/class/thermal",
        net_root: str | Path = "/sys/class/net",
        cpu_times_fn: Callable[[], Any] = psutil.cpu_times,
        memory_fn: Callable[[], Any] = psutil.virtual_memory,
        disk_usage_fn: Callable[[str], Any] = shutil.disk_usage,
        temperature_fn: Callable[[], dict[str, list[Any]]] | None = None,
        command_runner: Callable[..., Any] = subprocess.run,
        bluetoothctl_path: str | None = None,
        wall_time_fn: Callable[[], float] = time.time,
    ):
        self.disk_path = disk_path
        self.wifi_interface = wifi_interface
        self.thermal_root = Path(thermal_root)
        self.net_root = Path(net_root)
        self.cpu_times_fn = cpu_times_fn
        self.memory_fn = memory_fn
        self.disk_usage_fn = disk_usage_fn
        self.temperature_fn = temperature_fn or getattr(
            psutil,
            "sensors_temperatures",
            lambda: {},
        )
        self.command_runner = command_runner
        self.bluetoothctl_path = (
            shutil.which("bluetoothctl") if bluetoothctl_path is None else bluetoothctl_path
        )
        self.wall_time_fn = wall_time_fn
        self._previous_cpu_times: Any | None = None

    def sample(self) -> MetricsSnapshot:
        sampled_at = datetime.fromtimestamp(self.wall_time_fn(), timezone.utc).isoformat()
        return MetricsSnapshot(
            sampled_at=sampled_at,
            cpu=self._sample_cpu(),
            ram=self._sample_ram(),
            temperature=self._sample_temperature(),
            disk=self._sample_disk(),
            wifi=self._sample_wifi(),
            bluetooth=self._sample_bluetooth(),
        )

    def _sample_cpu(self) -> MetricStatus:
        try:
            current = self.cpu_times_fn()
        except (OSError, psutil.Error, ValueError):
            return MetricStatus(False, {"percent": None}, "cpu_read_failed")

        previous = self._previous_cpu_times
        self._previous_cpu_times = current
        if previous is None:
            return MetricStatus(False, {"percent": None}, "warming_up")
        try:
            percent = cpu_percent_from_times(previous, current)
        except ValueError:
            return MetricStatus(False, {"percent": None}, "invalid_cpu_counters")
        return MetricStatus(True, {"percent": round(percent, 2)})

    def _sample_ram(self) -> MetricStatus:
        try:
            memory = self.memory_fn()
            total = int(memory.total)
            available = int(memory.available)
        except (AttributeError, OSError, psutil.Error, TypeError, ValueError):
            return MetricStatus(
                False,
                {"total_bytes": None, "available_bytes": None, "used_percent": None},
                "ram_read_failed",
            )
        if total <= 0 or not 0 <= available <= total:
            return MetricStatus(
                False,
                {"total_bytes": None, "available_bytes": None, "used_percent": None},
                "invalid_ram_reading",
            )
        return MetricStatus(
            True,
            {
                "total_bytes": total,
                "available_bytes": available,
                "used_percent": round((total - available) * 100.0 / total, 2),
            },
        )

    def _sample_temperature(self) -> MetricStatus:
        candidates: list[tuple[float, str]] = []
        try:
            zones = sorted(self.thermal_root.glob("thermal_zone*"))
        except OSError:
            zones = []

        for zone in zones:
            try:
                zone_type = (zone / "type").read_text(encoding="utf-8").strip()
                if not self._is_cpu_soc_sensor(zone_type):
                    continue
                raw_temperature = int((zone / "temp").read_text(encoding="utf-8").strip())
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            temperature_c = raw_temperature / 1000.0
            if math.isfinite(temperature_c) and 0.0 <= temperature_c <= 150.0:
                candidates.append((temperature_c, zone_type))

        if not candidates:
            try:
                sensors = self.temperature_fn()
            except (OSError, NotImplementedError, psutil.Error):
                sensors = {}
            for group_name, entries in sensors.items():
                for index, entry in enumerate(entries):
                    label = str(getattr(entry, "label", "") or f"sensor-{index}")
                    if not (
                        self._is_cpu_soc_sensor(group_name)
                        or self._is_cpu_soc_sensor(label)
                    ):
                        continue
                    try:
                        temperature_c = float(entry.current)
                    except (AttributeError, TypeError, ValueError):
                        continue
                    if math.isfinite(temperature_c) and 0.0 <= temperature_c <= 150.0:
                        candidates.append((temperature_c, f"{group_name}:{label}"))

        if not candidates:
            return MetricStatus(
                False,
                {"celsius": None, "source": None},
                "cpu_soc_sensor_unavailable",
            )
        temperature_c, source = max(candidates, key=lambda candidate: candidate[0])
        return MetricStatus(
            True,
            {"celsius": round(temperature_c, 2), "source": source},
        )

    @staticmethod
    def _is_cpu_soc_sensor(name: str) -> bool:
        normalized = name.lower()
        return any(token in normalized for token in ("cpu", "soc", "amlogic", "aml", "package"))

    def _sample_disk(self) -> MetricStatus:
        try:
            usage = self.disk_usage_fn(self.disk_path)
            free_bytes = int(usage.free)
        except (AttributeError, OSError, TypeError, ValueError):
            return MetricStatus(
                False,
                {"path": self.disk_path, "free_bytes": None},
                "disk_read_failed",
            )
        if free_bytes < 0:
            return MetricStatus(
                False,
                {"path": self.disk_path, "free_bytes": None},
                "invalid_disk_reading",
            )
        return MetricStatus(True, {"path": self.disk_path, "free_bytes": free_bytes})

    def _sample_wifi(self) -> MetricStatus:
        try:
            interfaces = (
                [self.net_root / self.wifi_interface]
                if self.wifi_interface != "auto"
                else sorted(self.net_root.iterdir())
            )
        except OSError:
            return MetricStatus(False, {"connected": None}, "wifi_interfaces_unavailable")

        wireless = [
            interface
            for interface in interfaces
            if (interface / "wireless").exists() or (interface / "phy80211").exists()
        ]
        if not wireless:
            return MetricStatus(False, {"connected": None}, "wireless_interface_unavailable")

        try:
            operstate = (wireless[0] / "operstate").read_text(encoding="utf-8").strip().lower()
            carrier_path = wireless[0] / "carrier"
            carrier = carrier_path.read_text(encoding="utf-8").strip() if carrier_path.exists() else None
        except (OSError, UnicodeDecodeError):
            return MetricStatus(False, {"connected": None}, "wifi_state_unavailable")

        connected = operstate == "up" and (carrier is None or carrier == "1")
        return MetricStatus(True, {"connected": connected})

    def _sample_bluetooth(self) -> MetricStatus:
        if self.bluetoothctl_path is None:
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetoothctl_unavailable",
            )
        try:
            result = self.command_runner(
                [self.bluetoothctl_path, "show"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
        except FileNotFoundError:
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetoothctl_unavailable",
            )
        except subprocess.TimeoutExpired:
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetooth_query_timeout",
            )
        except OSError:
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetooth_query_failed",
            )

        output = f"{result.stdout or ''}\n{result.stderr or ''}"
        if "no default controller available" in output.lower():
            return MetricStatus(True, {"present": False, "powered": None})
        if result.returncode != 0:
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetooth_query_failed",
            )

        lines = [line.strip() for line in output.splitlines()]
        if not any(line.startswith("Controller ") for line in lines):
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetooth_controller_unrecognized",
            )
        powered_value = next(
            (
                line.partition(":")[2].strip().lower()
                for line in lines
                if line.startswith("Powered:")
            ),
            None,
        )
        if powered_value not in {"yes", "no"}:
            return MetricStatus(
                False,
                {"present": None, "powered": None},
                "bluetooth_power_state_unavailable",
            )
        return MetricStatus(True, {"present": True, "powered": powered_value == "yes"})
