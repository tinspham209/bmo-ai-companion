"""Pure animation helpers computed from state and time."""

from __future__ import annotations

import math


def idle_glow_alpha(t: float) -> int:
    base = 180
    swing = 27  # +-15%
    return int(base + swing * math.sin((2 * math.pi / 3.0) * t))


def pupil_breathe_scale(t: float) -> float:
    return 1.0 + 0.05 * math.sin((2 * math.pi / 3.0) * t)


def speaking_mouth_height(amplitude: float | None, t: float, base: int = 8, dynamic: int = 20) -> int:
    if amplitude is None:
        # fallback 8hz
        amp = 0.5 + 0.5 * math.sin((2 * math.pi * 8.0) * t)
    else:
        amp = max(0.0, min(1.0, amplitude))
    return int(base + amp * dynamic)

