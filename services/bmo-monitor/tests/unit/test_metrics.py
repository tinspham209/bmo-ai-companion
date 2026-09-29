from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import metrics
from metrics import SystemMetricsProvider, cpu_percent_from_times


def test_cpu_percent_uses_successive_counter_deltas():
    previous = SimpleNamespace(user=20, nice=0, system=0, idle=80, iowait=0)
    current = SimpleNamespace(user=30, nice=0, system=0, idle=90, iowait=0)
    assert cpu_percent_from_times(previous, current) == 50.0


@pytest.mark.parametrize(
    ("previous", "current"),
    [
        (
            SimpleNamespace(user=10, idle=90),
            SimpleNamespace(user=9, idle=100),
        ),
        (
            SimpleNamespace(user=0, idle=0),
            SimpleNamespace(user=0, idle=0),
        ),
        (
            SimpleNamespace(user=-1, idle=1),
            SimpleNamespace(user=0, idle=2),
        ),
    ],
)
def test_cpu_percent_rejects_invalid_counters(previous, current):
    with pytest.raises(ValueError):
        cpu_percent_from_times(previous, current)


def _write_wifi_interface(net_root: Path, name: str, operstate: str, carrier: str):
    interface = net_root / name
    (interface / "wireless").mkdir(parents=True)
    (interface / "operstate").write_text(operstate, encoding="utf-8")
    (interface / "carrier").write_text(carrier, encoding="utf-8")
    return interface


def test_provider_normalizes_all_available_metrics(tmp_path):
    thermal_root = tmp_path / "thermal"
    zone = thermal_root / "thermal_zone0"
    zone.mkdir(parents=True)
    (zone / "type").write_text("amlogic_cpu_thermal", encoding="utf-8")
    (zone / "temp").write_text("65000", encoding="utf-8")

    net_root = tmp_path / "net"
    _write_wifi_interface(net_root, "wlan9", "up", "1")
    cpu_samples = iter(
        [
            SimpleNamespace(user=20, nice=0, system=0, idle=80, iowait=0),
            SimpleNamespace(user=30, nice=0, system=0, idle=90, iowait=0),
        ]
    )

    provider = SystemMetricsProvider(
        disk_path="/",
        thermal_root=thermal_root,
        net_root=net_root,
        cpu_times_fn=lambda: next(cpu_samples),
        memory_fn=lambda: SimpleNamespace(total=1000, available=250),
        disk_usage_fn=lambda path: SimpleNamespace(free=750_000_000),
        temperature_fn=lambda: {},
        command_runner=lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="Controller AA:BB:CC:DD:EE:FF (public)\n\tPowered: yes\n",
            stderr="",
        ),
        bluetoothctl_path="/usr/bin/bluetoothctl",
        wall_time_fn=lambda: 1_700_000_000,
    )

    first = provider.sample()
    assert not first.cpu.available
    second = provider.sample()
    status = second.as_dict()

    assert status["last_sample_time"].endswith("+00:00")
    assert status["metrics"]["cpu"] == {"available": True, "percent": 50.0}
    assert status["metrics"]["ram"] == {
        "available": True,
        "total_bytes": 1000,
        "available_bytes": 250,
        "used_percent": 75.0,
    }
    assert status["metrics"]["temperature"]["celsius"] == 65.0
    assert status["metrics"]["temperature"]["source"] == "amlogic_cpu_thermal"
    assert status["metrics"]["disk"]["free_bytes"] == 750_000_000
    assert status["metrics"]["wifi"]["connected"] is True
    assert status["metrics"]["bluetooth"] == {
        "available": True,
        "present": True,
        "powered": True,
    }
    assert "AA:BB:CC:DD:EE:FF" not in str(status)


def test_temperature_uses_highest_cpu_soc_zone_and_ignores_unrelated_sensor(tmp_path):
    thermal_root = tmp_path / "thermal"
    for name, zone_type, raw in (
        ("thermal_zone0", "gpu_thermal", "90000"),
        ("thermal_zone1", "cpu_thermal", "60000"),
        ("thermal_zone2", "soc_thermal", "65000"),
    ):
        zone = thermal_root / name
        zone.mkdir(parents=True)
        (zone / "type").write_text(zone_type, encoding="utf-8")
        (zone / "temp").write_text(raw, encoding="utf-8")
    provider = SystemMetricsProvider(thermal_root=thermal_root)

    result = provider._sample_temperature()

    assert result.available
    assert result.values == {"celsius": 65.0, "source": "soc_thermal"}


def test_temperature_is_unavailable_without_cpu_soc_sensor(tmp_path):
    thermal_root = tmp_path / "thermal"
    zone = thermal_root / "thermal_zone0"
    zone.mkdir(parents=True)
    (zone / "type").write_text("gpu_thermal", encoding="utf-8")
    (zone / "temp").write_text("65000", encoding="utf-8")
    provider = SystemMetricsProvider(
        thermal_root=thermal_root,
        temperature_fn=lambda: {},
    )

    result = provider._sample_temperature()

    assert not result.available
    assert result.error == "cpu_soc_sensor_unavailable"


def test_temperature_uses_cpu_labeled_psutil_sensor_as_fallback(tmp_path):
    provider = SystemMetricsProvider(
        thermal_root=tmp_path / "missing-thermal",
        temperature_fn=lambda: {
            "coretemp": [SimpleNamespace(label="Package id 0", current=68.5)]
        },
    )

    result = provider._sample_temperature()

    assert result.available
    assert result.values == {"celsius": 68.5, "source": "coretemp:Package id 0"}


@pytest.mark.parametrize(
    ("operstate", "carrier", "connected"),
    [("up", "1", True), ("up", "0", False), ("down", "1", False)],
)
def test_wifi_link_state(operstate, carrier, connected, tmp_path):
    net_root = tmp_path / "net"
    _write_wifi_interface(net_root, "wlan0", operstate, carrier)
    provider = SystemMetricsProvider(net_root=net_root)

    result = provider._sample_wifi()

    assert result.available
    assert result.values["connected"] is connected


def test_wifi_missing_interface_is_explicit(tmp_path):
    net_root = tmp_path / "net"
    net_root.mkdir()
    provider = SystemMetricsProvider(net_root=net_root)

    result = provider._sample_wifi()

    assert not result.available
    assert result.error == "wireless_interface_unavailable"


def test_bluetooth_adapter_absence_is_distinct_from_query_failure():
    provider = SystemMetricsProvider(
        bluetoothctl_path="/usr/bin/bluetoothctl",
        command_runner=lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="No default controller available\n",
            stderr="",
        ),
    )

    result = provider._sample_bluetooth()

    assert result.available
    assert result.values == {"present": False, "powered": None}


def test_bluetooth_query_timeout_is_unavailable():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    provider = SystemMetricsProvider(
        bluetoothctl_path="/usr/bin/bluetoothctl",
        command_runner=timeout,
    )

    result = provider._sample_bluetooth()

    assert not result.available
    assert result.error == "bluetooth_query_timeout"


def test_bluetooth_command_unavailable_is_explicit(monkeypatch):
    monkeypatch.setattr(metrics.shutil, "which", lambda name: None)
    provider = SystemMetricsProvider(bluetoothctl_path=None)

    result = provider._sample_bluetooth()

    assert not result.available
    assert result.error == "bluetoothctl_unavailable"
