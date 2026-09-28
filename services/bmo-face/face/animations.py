"""Pure animation helpers computed from state and time."""

from __future__ import annotations

import math


def idle_glow_alpha(t: float, period_seconds: float = 3.0) -> int:
    base = 180
    swing = 27  # +-15%
    return int(base + swing * math.sin((2 * math.pi / period_seconds) * t))


def pupil_breathe_scale(t: float, period_seconds: float = 3.0) -> float:
    return 1.0 + 0.05 * math.sin((2 * math.pi / period_seconds) * t)


def sample_amplitude(envelope: list[float], sample_rate_hz: int, elapsed: float) -> float | None:
    if not envelope or sample_rate_hz <= 0 or elapsed < 0:
        return None
    position = elapsed * sample_rate_hz
    if position >= len(envelope):
        return 0.0
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(envelope) - 1)
    fraction = position - lower_index
    return envelope[lower_index] + (envelope[upper_index] - envelope[lower_index]) * fraction


def speaking_mouth_height(amplitude: float | None, t: float, base: int = 8, dynamic: int = 20) -> int:
    if amplitude is None:
        # fallback 8hz
        amp = 0.5 + 0.5 * math.sin((2 * math.pi * 8.0) * t)
    else:
        amp = max(0.0, min(1.0, amplitude))
    return int(base + amp * dynamic)
