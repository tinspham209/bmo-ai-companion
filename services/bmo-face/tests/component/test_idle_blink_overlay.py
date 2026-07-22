from face.state_machine import FaceState, FaceStateMachine


def test_blink_overlay_runs_without_replacing_base_state():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 3.0)
    sm.transition_boot_complete()
    assert sm.state == FaceState.IDLE
    now["t"] += 3.1
    sm.tick()
    assert sm.state == FaceState.IDLE
    assert sm.blink_active

