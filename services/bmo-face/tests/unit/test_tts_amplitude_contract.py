from face.animations import speaking_mouth_height
from face.state_machine import Event, FaceState, FaceStateMachine


def test_amplitude_payload_is_clamped():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/ai/speaking_start", {"amplitude": [-1.0, 0.4, 2.0], "sample_rate_hz": 10}))
    assert sm.state == FaceState.SPEAKING
    assert sm.speaking_amplitude == [0.0, 0.4, 1.0]


def test_speaking_fallback_8hz_changes_over_time():
    h1 = speaking_mouth_height(None, 0.00)
    h2 = speaking_mouth_height(None, 0.03)
    assert h1 != h2

