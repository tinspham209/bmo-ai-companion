from face.state_machine import Event, FaceState, FaceStateMachine


def test_alert_interrupts_speaking_and_resumes():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/ai/speaking_start", {"amplitude": [0.1]}))
    assert sm.state == FaceState.SPEAKING
    sm.handle_event(Event("bmo/notify/event", {"priority": "high", "message": "x"}))
    assert sm.state == FaceState.ALERT
    now["t"] += 5.1
    sm.tick()
    assert sm.state == FaceState.SPEAKING


def test_low_priority_coalesced_during_thinking():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/voice/wake_word", {}))
    assert sm.state == FaceState.THINKING
    sm.handle_event(Event("bmo/system/state", {"emotion": "stressed"}))
    sm.handle_event(Event("bmo/system/state", {"emotion": "hot"}))
    assert "bmo/system/state" in sm.pending_low_priority
    sm.handle_event(Event("bmo/ai/speaking_start", {"amplitude": [0.1]}))
    sm.handle_event(Event("bmo/ai/speaking_end", {}))
    assert sm.state in (FaceState.HOT, FaceState.IDLE)

