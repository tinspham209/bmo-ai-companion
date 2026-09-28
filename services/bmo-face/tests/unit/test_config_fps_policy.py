import tempfile
from pathlib import Path

import pytest

from config import load_config


def test_loads_fps_target_and_fallback():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bmo.yaml"
        p.write_text(
            "face:\n  fps_target: 30\n  fps_fallback: 24\n  sleep_timeout_seconds: 300\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        assert cfg.fps_target == 30
        assert cfg.fps_fallback == 24


def test_default_config_is_found_when_started_from_service_directory(monkeypatch):
    service_dir = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(service_dir)
    cfg = load_config()
    assert cfg.fps_target == 30
    assert cfg.api_port == 5200


def test_invalid_fps_fails():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bmo.yaml"
        p.write_text("face:\n  fps_target: 24\n  fps_fallback: 30\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(p)


@pytest.mark.parametrize(
    "yaml_text",
    [
        "face:\n  fps_target: 0\n",
        "face:\n  fps_target: 30\n  fps_fallback: 30\n",
        "face:\n  fps_target: 30\n  fps_fallback: 24\n  fullscreen: false\n  resolution: 0x240\n",
        "face:\n  fps_target: 30\n  fps_fallback: 24\n  fullscreen: 'false'\n",
    ],
)
def test_invalid_face_config_is_rejected(yaml_text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bmo.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(p)
