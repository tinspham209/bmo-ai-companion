import tempfile
from pathlib import Path

import pytest

from config import CameraConfig, load_config


def test_loads_camera_config_when_started_from_service_directory(monkeypatch):
    service_dir = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(service_dir)
    config = load_config()
    assert config.backend == "auto"
    assert config.active_fps == 30
    assert config.sleep_fps == 5
    assert config.face_absent_seconds == 10


def test_loads_explicit_active_fps():
    config = CameraConfig(active_fps=25)
    config.validate()
    assert config.active_fps == 25


@pytest.mark.parametrize(
    "overrides",
    [
        {"device_index": -1},
        {"active_fps": 0},
        {"sleep_fps": 0},
        {"analysis_width": 1},
        {"face_absent_seconds": 0},
        {"face_position_max_hz": 0},
        {"face_position_min_delta": 2.0},
        {"face_position_heartbeat_seconds": 0.6},
        {"motion_threshold_ratio": 2.0},
        {"no_motion_timeout_seconds": 0},
        {"face_state_url": "http://example.com/state"},
        {"api_port": 70000},
        {"mqtt_broker": "broker.example.com"},
        {"backend": "unknown-camera-backend"},
    ],
)
def test_invalid_camera_config_is_rejected(overrides):
    with pytest.raises(ValueError):
        CameraConfig(**overrides).validate()


def test_non_mapping_camera_config_is_rejected():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "bmo.yaml"
        path.write_text("camera: []\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping"):
            load_config(path)
