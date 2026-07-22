"""Procedural geometry builder for BMO face components."""

from __future__ import annotations

from dataclasses import dataclass

from .colors import ScaleContext


@dataclass(frozen=True)
class FaceLayout:
    screen_rect: tuple[int, int, int, int]
    left_eye_rect: tuple[int, int, int, int]
    right_eye_rect: tuple[int, int, int, int]
    mouth_rect: tuple[int, int, int, int]


def build_face_layout(screen_w: int, screen_h: int) -> FaceLayout:
    """Return scaled geometry for core face components."""
    s = ScaleContext(screen_w=screen_w, screen_h=screen_h)
    center_x = screen_w // 2
    center_y = screen_h // 2

    screen_w_px = s.scale(180)
    screen_h_px = s.scale(130)
    screen_x = center_x - (screen_w_px // 2)
    screen_y = center_y - (screen_h_px // 2)

    eye_w = s.scale(22)
    eye_h = s.scale(16)
    eye_gap = s.scale(30)
    eye_y = screen_y + s.scale(42)
    left_eye_x = center_x - eye_gap - eye_w
    right_eye_x = center_x + eye_gap

    mouth_w = s.scale(44)
    mouth_h = s.scale(12)
    mouth_x = center_x - (mouth_w // 2)
    mouth_y = screen_y + s.scale(88)

    return FaceLayout(
        screen_rect=(screen_x, screen_y, screen_w_px, screen_h_px),
        left_eye_rect=(left_eye_x, eye_y, eye_w, eye_h),
        right_eye_rect=(right_eye_x, eye_y, eye_w, eye_h),
        mouth_rect=(mouth_x, mouth_y, mouth_w, mouth_h),
    )

