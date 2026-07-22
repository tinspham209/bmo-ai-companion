"""Renderer runtime for bmo-face."""

from __future__ import annotations

import math
import signal
import threading
import time
from queue import Empty, Queue

from face.animations import idle_glow_alpha, pupil_breathe_scale, speaking_mouth_height
from face.colors import (
    COLOR_ALERT,
    COLOR_BODY,
    COLOR_DIM,
    COLOR_EYE,
    COLOR_EYE_PUPIL,
    COLOR_GLOW,
    COLOR_HOT_TINT,
    COLOR_MOUTH,
    COLOR_SAD_TINT,
    COLOR_SCREEN_BG,
    ScaleContext,
)
from face.components import build_face_layout
from face.state_machine import Event, FaceState, FaceStateMachine

try:
    import pygame
except Exception:  # pragma: no cover
    pygame = None


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


class FaceRuntime:
    def __init__(
        self,
        fps_target: int,
        fps_fallback: int,
        sleep_timeout_seconds: int,
        fullscreen: bool = True,
        resolution: str = "auto",
    ):
        self.fps_target = fps_target
        self.fps_fallback = fps_fallback
        self.current_fps = fps_target
        self.fullscreen = fullscreen
        self.resolution = resolution
        self.event_queue: Queue = Queue()
        self.sm = FaceStateMachine(sleep_timeout_seconds=sleep_timeout_seconds)
        self.running = False
        self._lock = threading.Lock()
        self.brightness_override: float | None = None
        self.publisher = None
        self._start_ts = time.monotonic()
        self._last_frame_dt = 0.0
        self._screen = None
        self._clock = None
        self._layout = None
        self._scale = None
        self._phase_start_ts = time.monotonic()

    def set_fps_fallback(self) -> None:
        self.current_fps = self.fps_fallback

    def set_publisher(self, publish_fn) -> None:
        self.publisher = publish_fn

    def dispatch(self, name: str, payload: dict):
        with self._lock:
            prev_state = self.sm.state
            self.sm.handle_event(Event(name=name, payload=payload))
            if self.sm.state != prev_state:
                self._phase_start_ts = self.now()

    def process_queue_once(self) -> None:
        while True:
            try:
                raw = self.event_queue.get_nowait()
            except Empty:
                break
            name = raw.get("name")
            payload = raw.get("payload", {})
            if name == "bmo/face/brightness":
                self.brightness_override = float(payload.get("level", 1.0))
                continue
            self.dispatch(name, payload)

    def tick(self) -> None:
        with self._lock:
            prev_state = self.sm.state
            self.sm.tick()
            if self.sm.state != prev_state:
                self._phase_start_ts = self.now()

    def current_state(self):
        with self._lock:
            return self.sm.state

    def current_notification(self) -> dict:
        with self._lock:
            return dict(self.sm.current_notification)

    def now(self) -> float:
        return time.monotonic()

    def pop_publish_events(self) -> list[dict]:
        out = []
        with self._lock:
            while self.sm.publish_queue:
                out.append(self.sm.publish_queue.popleft())
        return out

    def _display_size(self) -> tuple[int, int]:
        if self.resolution != "auto" and "x" in self.resolution:
            w, h = self.resolution.split("x", 1)
            return int(w), int(h)
        if pygame:
            info = pygame.display.Info()
            if info.current_w > 0 and info.current_h > 0:
                return info.current_w, info.current_h
        return (1024, 600)

    def _init_pygame(self) -> None:
        if not pygame:
            return
        pygame.init()
        w, h = self._display_size()
        flags = pygame.SCALED
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        self._screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption("BMO Face")
        self._clock = pygame.time.Clock()
        self._layout = build_face_layout(w, h)
        self._scale = ScaleContext(w, h)
        with self._lock:
            self.sm.transition_boot_complete()

    def _apply_brightness(self, color: tuple[int, int, int]) -> tuple[int, int, int]:
        level = 1.0 if self.brightness_override is None else max(0.0, min(1.0, self.brightness_override))
        return tuple(max(0, min(255, int(c * level))) for c in color)

    def _draw_rect(self, rect, color, border_radius=0):
        pygame.draw.rect(self._screen, self._apply_brightness(color), rect, border_radius=border_radius)

    def _draw_face(self) -> None:
        if not pygame or self._screen is None or self._layout is None or self._scale is None:
            return
        now = self.now()
        t = now - self._start_ts
        state = self.current_state()
        s = self._scale

        body      = _hex_to_rgb(COLOR_BODY)
        screen_bg = _hex_to_rgb(COLOR_SCREEN_BG)
        eye_c     = _hex_to_rgb(COLOR_EYE)
        pupil_c   = _hex_to_rgb(COLOR_EYE_PUPIL)
        mouth_c   = _hex_to_rgb(COLOR_MOUTH)

        # ── Background (BMO body colour) ──
        self._screen.fill(self._apply_brightness(body))

        # ── Screen panel ──
        sx, sy, sw, sh = self._layout.screen_rect
        br = s.scale(10)
        pygame.draw.rect(self._screen, self._apply_brightness(screen_bg),
                         (sx, sy, sw, sh), border_radius=br)

        # ── Glow outline for idle / wake / listening ──
        if state in (FaceState.IDLE, FaceState.WAKE, FaceState.LOOK_LEFT,
                     FaceState.LOOK_RIGHT, FaceState.LISTENING):
            glow_alpha = max(60, min(255, idle_glow_alpha(t)))
            glow_surf = pygame.Surface((sw + 4, sh + 4), pygame.SRCALPHA)
            g = _hex_to_rgb(COLOR_GLOW)
            pygame.draw.rect(glow_surf, (*g, glow_alpha), (0, 0, sw + 4, sh + 4),
                             border_radius=br + 2, width=s.scale(2))
            self._screen.blit(glow_surf, (sx - 2, sy - 2))

        # ── Eyes (ellipses, height scaled per state) ──
        lx, ly, lw, lh = self._layout.left_eye_rect
        rx, ry, rw, rh = self._layout.right_eye_rect

        eye_scale_y = 1.0
        if state in (FaceState.SLEEP, FaceState.SAD, FaceState.HAPPY):
            eye_scale_y = 0.35          # squint / closed
        elif state == FaceState.HOT:
            eye_scale_y = 0.7
        elif state in (FaceState.LISTENING, FaceState.ALERT):
            eye_scale_y = 1.45          # wide open
        elif state == FaceState.STRESSED:
            eye_scale_y = 1.2

        if self.sm.blink_active:
            eye_scale_y = min(eye_scale_y, 0.12)

        draw_lh = max(1, int(lh * eye_scale_y))
        draw_rh = max(1, int(rh * eye_scale_y))
        draw_ly = ly + (lh - draw_lh) // 2
        draw_ry = ry + (rh - draw_rh) // 2

        pygame.draw.ellipse(self._screen, self._apply_brightness(eye_c),
                            (lx, draw_ly, lw, draw_lh))
        pygame.draw.ellipse(self._screen, self._apply_brightness(eye_c),
                            (rx, draw_ry, rw, draw_rh))

        # ── Pupils ──
        pupil_offset_x = 0
        if state == FaceState.LOOK_LEFT:
            pupil_offset_x = -s.scale(4)
        elif state == FaceState.LOOK_RIGHT:
            pupil_offset_x = s.scale(4)
        elif state == FaceState.THINKING:
            pupil_offset_x = int(math.sin((2 * math.pi / 0.8) * t) * s.scale(4))
        elif state == FaceState.WORRIED:
            pupil_offset_x = int(math.sin((2 * math.pi / 0.4) * t) * s.scale(3))

        if state == FaceState.STRESSED:
            # X eyes — two crossing lines inside each eye rect (😵)
            line_w = max(2, s.scale(2))
            for (ex, ey_e, ew, eh) in [(lx, draw_ly, lw, draw_lh), (rx, draw_ry, rw, draw_rh)]:
                pad = max(1, ew // 5)
                pygame.draw.line(self._screen, self._apply_brightness(pupil_c),
                                 (ex + pad, ey_e + pad), (ex + ew - pad, ey_e + eh - pad), line_w)
                pygame.draw.line(self._screen, self._apply_brightness(pupil_c),
                                 (ex + ew - pad, ey_e + pad), (ex + pad, ey_e + eh - pad), line_w)
        elif draw_lh > 3:
            breathe = pupil_breathe_scale(t) if state in (FaceState.IDLE, FaceState.WAKE) else 1.0
            p_r = max(1, int(s.scale(4) * breathe))
            lpc = (lx + lw // 2 + pupil_offset_x, draw_ly + draw_lh // 2)
            rpc = (rx + rw // 2 + pupil_offset_x, draw_ry + draw_rh // 2)
            pygame.draw.circle(self._screen, self._apply_brightness(pupil_c), lpc, p_r)
            pygame.draw.circle(self._screen, self._apply_brightness(pupil_c), rpc, p_r)

        # ── Eyebrows ──
        brow_y = ly - s.scale(4)
        brow_lw = max(1, s.scale(2))
        if state == FaceState.WORRIED:
            # /\ inner-up (concerned)
            pygame.draw.line(self._screen, self._apply_brightness(eye_c),
                             (lx, brow_y + s.scale(3)), (lx + lw, brow_y), brow_lw)
            pygame.draw.line(self._screen, self._apply_brightness(eye_c),
                             (rx, brow_y), (rx + rw, brow_y + s.scale(3)), brow_lw)
        elif state == FaceState.STRESSED:
            # \/ inner-down (angry)
            pygame.draw.line(self._screen, self._apply_brightness(eye_c),
                             (lx, brow_y), (lx + lw, brow_y + s.scale(3)), brow_lw)
            pygame.draw.line(self._screen, self._apply_brightness(eye_c),
                             (rx, brow_y + s.scale(3)), (rx + rw, brow_y), brow_lw)
        elif state == FaceState.SAD:
            # \\ outer-down (sad)
            pygame.draw.line(self._screen, self._apply_brightness(eye_c),
                             (lx, brow_y), (lx + lw, brow_y + s.scale(3)), brow_lw)
            pygame.draw.line(self._screen, self._apply_brightness(eye_c),
                             (rx, brow_y + s.scale(3)), (rx + rw, brow_y), brow_lw)

        # ── Mouth ──
        mx, my_m, mw, mh = self._layout.mouth_rect
        lw_m = max(1, s.scale(2))

        if state in (FaceState.HAPPY, FaceState.WAKE):
            # Smile: π→2π = bottom arc in pygame y-down coords
            arc_rect = (mx - s.scale(2), my_m - s.scale(6), mw + s.scale(4), s.scale(24))
            pygame.draw.arc(self._screen, self._apply_brightness(mouth_c),
                            arc_rect, math.pi, math.pi * 2, lw_m * 2)
        elif state == FaceState.SAD:
            # Frown: 0→π = top arc in pygame y-down coords
            arc_rect = (mx - s.scale(2), my_m, mw + s.scale(4), s.scale(24))
            pygame.draw.arc(self._screen, self._apply_brightness(mouth_c),
                            arc_rect, 0, math.pi, lw_m * 2)
        elif state == FaceState.SPEAKING:
            # Animated oval — always uses 8 Hz fallback for visible oscillation
            h = s.scale(speaking_mouth_height(None, t, base=5, dynamic=16))
            oval_y = my_m + mh // 2 - h // 2
            pygame.draw.ellipse(self._screen, self._apply_brightness(mouth_c),
                                (mx + s.scale(6), oval_y, mw - s.scale(12), max(s.scale(4), h)))
        elif state in (FaceState.THINKING, FaceState.LISTENING):
            # Small open oval
            pygame.draw.ellipse(self._screen, self._apply_brightness(mouth_c),
                                (mx + s.scale(8), my_m + s.scale(2), mw - s.scale(16), s.scale(8)))
        elif state == FaceState.ALERT:
            # Wide open "O"
            pygame.draw.ellipse(self._screen, self._apply_brightness(mouth_c),
                                (mx + s.scale(4), my_m - s.scale(2), mw - s.scale(8), s.scale(14)))
        elif state == FaceState.STRESSED:
            # Zigzag mouth
            steps = 8
            pts = [
                (mx + int(i * mw / steps),
                 my_m + mh // 2 + (s.scale(3) if i % 2 == 0 else -s.scale(3)))
                for i in range(steps + 1)
            ]
            pygame.draw.lines(self._screen, self._apply_brightness(mouth_c), False, pts, lw_m)
        else:
            # Default: thin flat line
            pygame.draw.rect(self._screen, self._apply_brightness(mouth_c),
                             (mx, my_m + mh // 2 - max(1, s.scale(1)), mw, max(1, s.scale(2))),
                             border_radius=s.scale(2))

        # ── Thinking dots (pulsing, staggered) ──
        if state == FaceState.THINKING:
            dot_y = my_m + s.scale(22)
            for i in range(3):
                phase_t = t - i * 0.2
                pulse = 0.5 + 0.5 * math.sin((2 * math.pi * 1.5) * phase_t)
                r = max(2, int(s.scale(3) + s.scale(2) * pulse))
                cx = mx + s.scale(4 + i * 14)
                pygame.draw.circle(self._screen, self._apply_brightness(mouth_c), (cx, dot_y), r)

        # ── State-specific overlays ──
        if state == FaceState.HOT:
            tint = pygame.Surface((sw, sh), pygame.SRCALPHA)
            r, g, b = _hex_to_rgb(COLOR_HOT_TINT)
            tint.fill((r, g, b, 45))
            self._screen.blit(tint, (sx, sy))
            drop_r = max(2, s.scale(3))
            for ddx, ddy in [(sw - s.scale(14), s.scale(10)), (sw - s.scale(7), s.scale(22))]:
                pygame.draw.circle(self._screen, (90, 170, 255), (sx + ddx, sy + ddy), drop_r)

        elif state == FaceState.SAD:
            tint = pygame.Surface((sw, sh), pygame.SRCALPHA)
            r, g, b = _hex_to_rgb(COLOR_SAD_TINT)
            tint.fill((r, g, b, 40))
            self._screen.blit(tint, (sx, sy))

        elif state == FaceState.SLEEP:
            dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
            r, g, b = _hex_to_rgb(COLOR_DIM)
            dim.fill((r, g, b, 170))
            self._screen.blit(dim, (sx, sy))
            if pygame.font.get_init():
                for zx_off, zy_off, z_size in [
                    (sw - s.scale(28), s.scale(8),  s.scale(14)),
                    (sw - s.scale(18), s.scale(20), s.scale(11)),
                    (sw - s.scale(10), s.scale(32), s.scale(9)),
                ]:
                    fz = pygame.font.Font(None, max(10, z_size))
                    zs = fz.render("z", True, (170, 170, 255))
                    self._screen.blit(zs, (sx + zx_off, sy + zy_off))

        elif state == FaceState.ALERT:
            # Flashing coloured border
            flash_alpha = int(abs(math.sin(t * 5)) * 160)
            border_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            alert_c = _hex_to_rgb(COLOR_ALERT)
            pygame.draw.rect(border_surf, (*alert_c, flash_alpha), (0, 0, sw, sh),
                             border_radius=br, width=s.scale(3))
            self._screen.blit(border_surf, (sx, sy))
            if pygame.font.get_init():
                f_exc = pygame.font.Font(None, max(12, s.scale(20)))
                exc_s = f_exc.render("!", True, self._apply_brightness(alert_c))
                self._screen.blit(exc_s, (sx + sw // 2 - exc_s.get_width() // 2, sy + s.scale(5)))

        # ── Notification text box (inside screen panel, bottom) ──
        if state == FaceState.ALERT and pygame.font.get_init():
            notif = self.current_notification()
            if notif:
                title   = notif.get("title", "")
                message = notif.get("message", "")
                box_h   = s.scale(36) if (title and message) else s.scale(22)
                box_x   = sx + s.scale(3)
                box_w   = sw - s.scale(6)
                box_y   = sy + sh - s.scale(2) - box_h
                box_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
                box_surf.fill((15, 15, 35, 210))
                alert_c = _hex_to_rgb(COLOR_ALERT)
                pygame.draw.rect(box_surf, (*alert_c, 150), (0, 0, box_w, box_h),
                                 border_radius=s.scale(5), width=1)
                self._screen.blit(box_surf, (box_x, box_y))
                if title:
                    ft = pygame.font.Font(None, max(12, s.scale(14)))
                    ts = ft.render(title, True, (255, 220, 80))
                    self._screen.blit(ts, (box_x + s.scale(4), box_y + s.scale(3)))
                if message:
                    fm = pygame.font.Font(None, max(10, s.scale(12)))
                    ms = fm.render(message, True, (210, 210, 210))
                    msg_y = box_y + (s.scale(20) if title else s.scale(4))
                    self._screen.blit(ms, (box_x + s.scale(4), msg_y))

        pygame.display.flip()

    def run(self) -> None:  # pragma: no cover
        self.running = True
        self._init_pygame()
        frame_sleep = 1.0 / max(1, self.current_fps)
        while self.running:
            if pygame:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.stop()
            self.process_queue_once()
            self.tick()
            for evt in self.pop_publish_events():
                if self.publisher:
                    self.publisher(evt["topic"], evt["payload"])
            self._draw_face()
            if self._clock:
                self._clock.tick(self.current_fps)
            else:
                time.sleep(frame_sleep)
        if pygame:
            pygame.quit()

    def stop(self) -> None:
        self.running = False


def install_signal_handlers(runtime: FaceRuntime):
    def _handle_sigterm(signum, frame):  # pragma: no cover
        runtime.stop()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
