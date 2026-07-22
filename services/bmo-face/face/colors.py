"""Color tokens and scaling helpers for bmo-face."""

from __future__ import annotations

from dataclasses import dataclass

COLOR_BODY = "#78C8C8"
COLOR_SCREEN_BG = "#1a1a2e"
COLOR_EYE = "#FFFFFF"
COLOR_EYE_PUPIL = "#00FF88"
COLOR_MOUTH = "#00FF88"
COLOR_GLOW = "#78C8C8"
COLOR_DIM = "#0D0D1A"
COLOR_HOT_TINT = "#FF4422"
COLOR_ALERT = "#FFDD00"
COLOR_SAD_TINT = "#4488CC"


@dataclass(frozen=True)
class ScaleContext:
    """Normalized scaling context based on baseline short-side pixels."""

    screen_w: int
    screen_h: int
    baseline: int = 240

    @property
    def factor(self) -> float:
        short_side = min(self.screen_w, self.screen_h)
        return short_side / float(self.baseline)

    def scale(self, value: float) -> int:
        return max(1, int(value * self.factor))

