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


def test_invalid_fps_fails():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bmo.yaml"
        p.write_text("face:\n  fps_target: 24\n  fps_fallback: 30\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(p)

