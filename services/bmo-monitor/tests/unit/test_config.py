from pathlib import Path
import tempfile

import pytest

from config import MonitorConfig, load_config


def test_loads_monitor_config_from_shared_file():
    service_dir = Path(__file__).resolve().parents[2]
    config = load_config(service_dir.parents[1] / "config" / "bmo.yaml")
    assert config.sample_interval_seconds == 5.0
    assert config.emotion_reassert_interval_seconds == 2.0
    assert config.disk_worried_free_bytes == 500_000_000
    assert config.api_port == 5202
    assert config.wifi_interface == "auto"


def test_loads_defaults_when_monitor_section_is_missing():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bmo.yaml"
        path.write_text("face: {}\n", encoding="utf-8")
        config = load_config(path)
    assert config == MonitorConfig()


@pytest.mark.parametrize(
    "overrides",
    [
        {"sample_interval_seconds": 0},
        {"sample_interval_seconds": 301},
        {"emotion_reassert_interval_seconds": 2.01},
        {"cpu_stress_percent": 79},
        {"temperature_hot_c": 71},
        {"disk_worried_free_bytes": 500_000_001},
        {"disk_path": "relative"},
        {"api_port": 70000},
        {"mqtt_broker": "broker.example.com"},
        {"mqtt_port": 0},
        {"wifi_interface": "../wlan0"},
    ],
)
def test_invalid_monitor_config_is_rejected(overrides):
    with pytest.raises(ValueError):
        MonitorConfig(**overrides).validate()


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("monitor: []\n", "monitor configuration"),
        ("monitor:\n  sample_interval_seconds: true\n", "must be a number"),
        ("monitor:\n  api_port: true\n", "must be an integer"),
    ],
)
def test_invalid_yaml_shapes_and_types_are_rejected(contents, message):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bmo.yaml"
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_config(path)
