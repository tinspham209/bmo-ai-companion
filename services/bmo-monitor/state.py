"""Deterministic mapping from system readings to face emotions."""

from __future__ import annotations

import math
from typing import Literal


Emotion = Literal["happy", "stressed", "hot", "worried"]


def select_emotion(
    cpu_percent: float | None,
    temperature_c: float | None,
    disk_free_bytes: int | None,
) -> Emotion | None:
    """Return the highest-priority current emotion, or None if inputs are incomplete."""
    if not _valid_number(cpu_percent) or not _valid_number(temperature_c):
        return None
    if (
        isinstance(disk_free_bytes, bool)
        or not isinstance(disk_free_bytes, int)
        or disk_free_bytes < 0
    ):
        return None

    if temperature_c > 70.0:
        return "hot"
    if cpu_percent > 80.0:
        return "stressed"
    if disk_free_bytes < 500_000_000:
        return "worried"
    return "happy"


def _valid_number(value: float | None) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )
