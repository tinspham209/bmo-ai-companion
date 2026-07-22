from face.state_machine import Event, FaceState, FaceStateMachine


def test_alert_from_idle_returns_to_idle():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/notify/event", {"priority": "high"}))
    assert sm.state == FaceState.ALERT
    now["t"] += 5.1
    sm.tick()
    assert sm.state == FaceState.IDLE

