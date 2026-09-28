import pygame

from face.colors import ScaleContext
from face.components import build_face_layout
from renderer import FaceRuntime


def test_renderer_draws_states_at_target_resolutions(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    try:
        for width, height in ((320, 240), (1920, 1080)):
            runtime = FaceRuntime(fps_target=30, fps_fallback=24, sleep_timeout_seconds=300)
            runtime._screen = pygame.display.set_mode((width, height))
            runtime._layout = build_face_layout(width, height)
            runtime._scale = ScaleContext(width, height)
            runtime._shake_surface = pygame.Surface((width, height))
            runtime.sm.transition_boot_complete()

            runtime.dispatch("bmo/face/set_state", {"state": "boot"})
            runtime._draw_face()
            for elapsed in (0.4, 0.75, 1.15):
                runtime._phase_start_ts = runtime.now() - elapsed
                runtime._draw_face()

            for state in (
                "idle",
                "happy",
                "sad",
                "stressed",
                "hot",
                "worried",
                "thinking",
                "listening",
                "speaking",
                "alert",
                "sleep",
                "wake",
            ):
                runtime.dispatch("bmo/face/set_state", {"state": state})
                runtime._draw_face()
            runtime.dispatch("bmo/notify/event", {
                "priority": "high",
                "title": "A notification title long enough to need truncation",
                "message": "A long notification message that should remain inside the face panel",
            })
            runtime._draw_face()
    finally:
        pygame.quit()
