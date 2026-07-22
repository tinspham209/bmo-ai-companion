from face.state_machine import FaceState
from renderer import FaceRuntime


def test_runtime_processes_event_queue_and_state_publish():
    rt = FaceRuntime(fps_target=30, fps_fallback=24, sleep_timeout_seconds=300)
    rt.dispatch("bmo/voice/wake_word", {})
    assert rt.current_state() == FaceState.THINKING
    out = rt.pop_publish_events()
    assert any(e["topic"] == "bmo/face/state" for e in out)

