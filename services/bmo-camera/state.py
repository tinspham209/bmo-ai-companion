"""Presence, position, and motion state transitions for bmo-camera."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

from config import CameraConfig
from detector import FaceDetection

_TIME_EPSILON = 1e-9


@dataclass(frozen=True)
class CameraEvent:
    topic: str
    payload: dict[str, Any]


class CameraEventTracker:
    def __init__(
        self,
        config: CameraConfig,
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self.config = config
        self.now_fn = now_fn
        started_at = now_fn()
        self.presence_state = "unknown"
        self.motion_state = "unknown"
        self._absence_since = started_at
        self._no_motion_since = started_at
        self._motion_positive_streak = 0
        self._last_position_x: float | None = None
        self._last_position_published_at: float | None = None
        self._last_event_topic: str | None = None
        self._last_event_at: float | None = None
        self._last_face_seen_at: float | None = None
        self._last_motion_at: float | None = None
        self._camera_ready = False
        self._paused_at: float | None = None

    def mark_camera_ready(self, now: float | None = None) -> None:
        now = self.now_fn() if now is None else now
        if self._camera_ready:
            return
        self._camera_ready = True
        self._absence_since = now
        self._no_motion_since = now
        self._paused_at = None

    def pause_timers(self, now: float | None = None) -> None:
        if self._paused_at is None:
            self._paused_at = self.now_fn() if now is None else now

    def resume_timers(self, now: float | None = None) -> None:
        if self._paused_at is None:
            return
        now = self.now_fn() if now is None else now
        paused_duration = max(0.0, now - self._paused_at)
        if self._absence_since is not None:
            self._absence_since += paused_duration
        if self._no_motion_since is not None:
            self._no_motion_since += paused_duration
        if self._last_position_published_at is not None:
            self._last_position_published_at += paused_duration
        self._paused_at = None

    def update(
        self,
        face: FaceDetection | None,
        motion_score: float,
        now: float | None = None,
    ) -> list[CameraEvent]:
        now = self.now_fn() if now is None else now
        events: list[CameraEvent] = []

        if face is not None:
            if self.presence_state != "present":
                events.append(self._event("bmo/camera/person_detected", {}, now))
                self.presence_state = "present"
            self._absence_since = None
            self._last_face_seen_at = now
            self._maybe_publish_position(face, now, events)
        else:
            if self.presence_state == "present" and self._absence_since is None:
                self._absence_since = now
            elif self._absence_since is None:
                self._absence_since = now
            if (
                self.presence_state != "absent"
                and self._absence_since is not None
                and now - self._absence_since + _TIME_EPSILON >= self.config.face_absent_seconds
            ):
                events.append(self._event("bmo/camera/person_left", {}, now))
                self.presence_state = "absent"
                self._last_position_x = None
                self._last_position_published_at = None

        events.extend(self._update_motion(motion_score, now))
        return events

    def _maybe_publish_position(
        self,
        face: FaceDetection,
        now: float,
        events: list[CameraEvent],
    ) -> None:
        last_sent = self._last_position_published_at
        rate_interval = 1.0 / self.config.face_position_max_hz
        rate_ready = last_sent is None or now - last_sent + _TIME_EPSILON >= rate_interval
        changed = self._last_position_x is None or abs(face.x_center - self._last_position_x) >= self.config.face_position_min_delta
        heartbeat_due = (
            last_sent is None
            or now - last_sent + _TIME_EPSILON >= self.config.face_position_heartbeat_seconds
        )
        if rate_ready and (changed or heartbeat_due):
            events.append(
                self._event(
                    "bmo/camera/face_position",
                    {"x": max(0.0, min(1.0, float(face.x_center)))},
                    now,
                )
            )
            self._last_position_x = float(face.x_center)
            self._last_position_published_at = now

    def _update_motion(self, score: float, now: float) -> list[CameraEvent]:
        if not 0.0 <= score <= 1.0:
            raise ValueError("motion score must be in [0.0, 1.0]")

        events: list[CameraEvent] = []
        if score >= self.config.motion_threshold_ratio:
            self._motion_positive_streak += 1
            self._no_motion_since = None
            self._last_motion_at = now
            if self.motion_state != "motion" and self._motion_positive_streak >= 2:
                events.append(self._event("bmo/camera/motion", {}, now))
                self.motion_state = "motion"
        else:
            self._motion_positive_streak = 0
            if self.motion_state == "motion" and self._no_motion_since is None:
                self._no_motion_since = now
            elif self._no_motion_since is None:
                self._no_motion_since = now
            if (
                self.motion_state != "no_motion"
                and self._no_motion_since is not None
                and now - self._no_motion_since + _TIME_EPSILON >= self.config.no_motion_timeout_seconds
            ):
                events.append(self._event("bmo/camera/no_motion", {}, now))
                self.motion_state = "no_motion"
        return events

    def _event(self, topic: str, payload: dict[str, Any], now: float) -> CameraEvent:
        self._last_event_topic = topic
        self._last_event_at = now
        return CameraEvent(topic=topic, payload=payload)

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = self.now_fn() if now is None else now
        return {
            "presence": self.presence_state,
            "motion": self.motion_state,
            "last_face_seen_seconds_ago": (
                None if self._last_face_seen_at is None else max(0.0, now - self._last_face_seen_at)
            ),
            "last_motion_seconds_ago": (
                None if self._last_motion_at is None else max(0.0, now - self._last_motion_at)
            ),
            "last_event_topic": self._last_event_topic,
            "last_event_seconds_ago": (
                None if self._last_event_at is None else max(0.0, now - self._last_event_at)
            ),
        }
