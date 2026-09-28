"""State machine for bmo-face."""

from __future__ import annotations

import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any


class FaceState(StrEnum):
    BOOT = "boot"
    IDLE = "idle"
    LOOK_LEFT = "look_left"
    LOOK_RIGHT = "look_right"
    SLEEP = "sleep"
    WAKE = "wake"
    HAPPY = "happy"
    THINKING = "thinking"
    LISTENING = "listening"
    SPEAKING = "speaking"
    SAD = "sad"
    STRESSED = "stressed"
    HOT = "hot"
    WORRIED = "worried"
    ALERT = "alert"


PRIORITY: dict[FaceState, int] = {
    FaceState.ALERT: 6,
    FaceState.SPEAKING: 5,
    FaceState.THINKING: 4,
    FaceState.LISTENING: 4,
    FaceState.HAPPY: 3,
    FaceState.SAD: 3,
    FaceState.STRESSED: 3,
    FaceState.HOT: 3,
    FaceState.WORRIED: 3,
    FaceState.LOOK_LEFT: 3,
    FaceState.LOOK_RIGHT: 3,
    FaceState.IDLE: 2,
    FaceState.WAKE: 2,
    FaceState.BOOT: 2,
    FaceState.SLEEP: 1,
}


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (isinstance(value, int) or isfinite(value))
    )


@dataclass
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class FaceStateMachine:
    sleep_timeout_seconds: int = 300
    now_fn: Callable[[], float] = time.monotonic
    random_fn: Callable[[float, float], float] = random.uniform
    boot_duration_seconds: float = 1.3
    state: FaceState = FaceState.BOOT
    previous_state: FaceState | None = None
    speaking_was_interrupted: bool = False
    boot_deadline: float | None = None
    sleep_deadline: float | None = None
    look_center_deadline: float | None = None
    transient_deadline: float | None = None
    blink_next_deadline: float | None = None
    blink_started_at: float | None = None
    blink_active_until: float | None = None
    pending_low_priority: dict[str, Event] = field(default_factory=dict)
    state_history: list[FaceState] = field(default_factory=list)
    publish_queue: deque[dict[str, Any]] = field(default_factory=deque)
    speaking_amplitude: list[float] = field(default_factory=list)
    speaking_sample_rate_hz: int = 10
    speaking_started_at: float | None = None
    current_notification: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.state_history.append(self.state)
        now = self.now_fn()
        self.blink_next_deadline = now + self.random_fn(3.0, 6.0)
        if self.state == FaceState.BOOT:
            self.boot_deadline = now + self.boot_duration_seconds

    def _set_state(self, state: FaceState) -> None:
        if state == self.state:
            return
        self.previous_state = self.state
        self.state = state
        self.state_history.append(state)
        self.publish_queue.append({"topic": "bmo/face/state", "payload": {"state": state.value}})

    def transition_boot_complete(self) -> None:
        if self.state == FaceState.BOOT:
            self.boot_deadline = None
            self._set_state(FaceState.IDLE)
            self.publish_queue.append({"topic": "bmo/face/ready", "payload": {}})

    def handle_event(self, event: Event) -> None:
        if event.name == "bmo/face/set_state":
            self.pending_low_priority.clear()
            self._apply_event(event)
            return
        if event.name in ("bmo/camera/person_left", "bmo/camera/person_detected"):
            self._apply_event(event)
            return
        if self.state == FaceState.ALERT and event.name == "bmo/ai/speaking_end":
            self.speaking_was_interrupted = False
            self.speaking_amplitude.clear()
            self.speaking_started_at = None
            return

        current_priority = PRIORITY.get(self.state, 2)
        incoming_priority = self._event_priority(event)
        if self.state == FaceState.ALERT and incoming_priority < PRIORITY[FaceState.ALERT]:
            self._coalesce(event)
            return
        if self.state in (FaceState.SPEAKING, FaceState.THINKING, FaceState.LISTENING) and incoming_priority < current_priority:
            self._coalesce(event)
            return

        self._apply_event(event)

    def _coalesce(self, event: Event) -> None:
        self.pending_low_priority.pop(event.name, None)
        self.pending_low_priority[event.name] = event

    def _event_priority(self, event: Event) -> int:
        if event.name == "bmo/notify/event" and event.payload.get("priority") == "high":
            return 6
        if event.name in ("bmo/ai/speaking_start", "bmo/ai/speaking_end"):
            return 5
        if event.name in ("bmo/voice/wake_word", "bmo/voice/listening_start", "bmo/ai/proactive_start"):
            return 4
        if event.name.startswith("bmo/system/") or event.name.startswith("bmo/camera/face_position") or event.name == "bmo/voice/bt_disconnect":
            return 3
        return 2

    def _apply_event(self, event: Event) -> None:
        if event.name == "bmo/camera/person_left":
            self.sleep_deadline = self.now_fn() + self.sleep_timeout_seconds
            return
        if event.name == "bmo/camera/person_detected":
            self.sleep_deadline = None
            if self.state == FaceState.SLEEP:
                self._set_state(FaceState.WAKE)
                self.transient_deadline = self.now_fn() + 1.0
                self.look_center_deadline = None
            return
        if event.name == "bmo/camera/face_position":
            self._handle_face_position(event.payload)
            return
        if event.name in ("bmo/voice/wake_word", "bmo/ai/proactive_start"):
            self._set_state(FaceState.THINKING)
            self.transient_deadline = None
            return
        if event.name == "bmo/ai/speaking_start":
            amp = event.payload.get("amplitude")
            if isinstance(amp, list) and all(
                _is_finite_number(value)
                for value in amp
            ):
                self.speaking_amplitude = [float(max(0.0, min(1.0, value))) for value in amp]
            else:
                self.speaking_amplitude = []
            rate = event.payload.get("sample_rate_hz", 10)
            self.speaking_sample_rate_hz = (
                rate
                if isinstance(rate, int) and not isinstance(rate, bool) and 1 <= rate <= 1000
                else 10
            )
            self.speaking_started_at = self.now_fn()
            self.transient_deadline = None
            self._set_state(FaceState.SPEAKING)
            return
        if event.name == "bmo/ai/speaking_end":
            self._set_state(FaceState.IDLE)
            self.transient_deadline = None
            self.speaking_amplitude.clear()
            self.speaking_started_at = None
            self._flush_coalesced()
            return
        if event.name == "bmo/system/state":
            emotion = str(event.payload.get("emotion", "")).lower()
            mapping = {
                "happy": (FaceState.HAPPY, 3.0),
                "stressed": (FaceState.STRESSED, 5.0),
                "hot": (FaceState.HOT, 5.0),
                "worried": (FaceState.WORRIED, 5.0),
            }
            mapped = mapping.get(emotion)
            if mapped:
                self._set_state(mapped[0])
                self.transient_deadline = self.now_fn() + mapped[1]
            return
        if event.name == "bmo/voice/bt_disconnect":
            self._set_state(FaceState.SAD)
            self.transient_deadline = self.now_fn() + 4.0
            return
        if event.name == "bmo/notify/event" and event.payload.get("priority") == "high":
            title = event.payload.get("title", "")
            message = event.payload.get("message", "")
            if not isinstance(title, str) or not isinstance(message, str):
                return
            if self.state == FaceState.SPEAKING:
                self.speaking_was_interrupted = True
            self.current_notification = {
                "title": title,
                "message": message,
            }
            self._set_state(FaceState.ALERT)
            self.transient_deadline = self.now_fn() + 5.0
            return
        if event.name == "bmo/voice/listening_start":
            if self.state == FaceState.SLEEP:
                return
            self._set_state(FaceState.LISTENING)
            self.transient_deadline = self.now_fn() + 10.0
            return
        if event.name == "bmo/face/set_state":
            state_name = str(event.payload.get("state", "")).lower()
            try:
                forced = FaceState(state_name)
            except ValueError:
                return
            self.speaking_was_interrupted = False
            self.speaking_amplitude.clear()
            self.speaking_started_at = None
            self._set_state(forced)
            self.boot_deadline = self.now_fn() + self.boot_duration_seconds if forced == FaceState.BOOT else None
            # Safety timeout for transient states set manually (no pipeline end event)
            if forced == FaceState.SPEAKING:
                self.transient_deadline = self.now_fn() + 15.0
                self.speaking_started_at = self.now_fn()
            elif forced in (FaceState.THINKING, FaceState.LISTENING):
                self.transient_deadline = self.now_fn() + 10.0
            elif forced in (FaceState.HAPPY, FaceState.SAD, FaceState.STRESSED,
                            FaceState.HOT, FaceState.WORRIED, FaceState.ALERT,
                            FaceState.WAKE):
                self.transient_deadline = self.now_fn() + 5.0
            else:
                self.transient_deadline = None

    def _handle_face_position(self, payload: dict[str, Any]) -> None:
        x = payload.get("x")
        if not _is_finite_number(x) or not 0.0 <= x <= 1.0:
            return
        x = float(x)
        if x < 0.4:
            self._set_state(FaceState.LOOK_LEFT)
        elif x > 0.6:
            self._set_state(FaceState.LOOK_RIGHT)
        else:
            self._set_state(FaceState.IDLE)
        self.look_center_deadline = self.now_fn() + 0.5
        self.transient_deadline = None

    def _flush_coalesced(self) -> None:
        if not self.pending_low_priority:
            return
        pending = list(self.pending_low_priority.values())
        self.pending_low_priority.clear()
        for event in pending:
            self._apply_event(event)

    def tick(self) -> None:
        now = self.now_fn()
        if self.boot_deadline is not None and now >= self.boot_deadline:
            self.transition_boot_complete()
        if (
            self.sleep_deadline is not None
            and now >= self.sleep_deadline
            and self.state not in (FaceState.SLEEP, FaceState.WAKE)
            and PRIORITY.get(self.state, 2) <= PRIORITY[FaceState.WAKE]
        ):
            self._set_state(FaceState.SLEEP)
            self.sleep_deadline = None
        if self.look_center_deadline is not None and now >= self.look_center_deadline and self.state in (FaceState.LOOK_LEFT, FaceState.LOOK_RIGHT):
            self._set_state(FaceState.IDLE)
            self.look_center_deadline = None
        if self.transient_deadline is not None and now >= self.transient_deadline:
            previous_state = self.state
            if self.state == FaceState.ALERT and self.speaking_was_interrupted:
                self._set_state(FaceState.SPEAKING)
                self.speaking_was_interrupted = False
            elif self.state == FaceState.WAKE:
                self._set_state(FaceState.IDLE)
            elif self.state in (FaceState.HAPPY, FaceState.SAD, FaceState.STRESSED, FaceState.HOT,
                                FaceState.WORRIED, FaceState.ALERT, FaceState.LISTENING,
                                FaceState.SPEAKING, FaceState.THINKING):
                self._set_state(FaceState.IDLE)
            self.transient_deadline = None
            if previous_state in (FaceState.ALERT, FaceState.SPEAKING, FaceState.THINKING, FaceState.LISTENING) and self.state == FaceState.IDLE:
                self._flush_coalesced()
        if self.blink_next_deadline is not None and now >= self.blink_next_deadline and self.state != FaceState.SLEEP:
            self.blink_started_at = now
            self.blink_active_until = now + 0.2
            self.blink_next_deadline = now + self.random_fn(3.0, 6.0)
        if self.blink_active_until is not None and now >= self.blink_active_until:
            self.blink_started_at = None
            self.blink_active_until = None

    @property
    def blink_active(self) -> bool:
        return self.blink_active_until is not None and self.now_fn() < self.blink_active_until

    @property
    def blink_eye_scale(self) -> float:
        if self.blink_started_at is None or self.blink_active_until is None:
            return 1.0
        elapsed = self.now_fn() - self.blink_started_at
        if elapsed < 0.075:
            return 1.0 - 0.88 * (elapsed / 0.075)
        if elapsed < 0.125:
            return 0.12
        return 0.12 + 0.88 * min(1.0, (elapsed - 0.125) / 0.075)
