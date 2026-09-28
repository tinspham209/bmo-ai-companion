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


def test_direct_set_state_bypasses_coalescing_and_discards_stale_events():
    sm = FaceStateMachine(random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/voice/wake_word"))
    sm.handle_event(Event("bmo/system/state", {"emotion": "hot"}))
    sm.handle_event(Event("bmo/face/set_state", {"state": "happy"}))
    assert sm.state == FaceState.HAPPY
    assert not sm.pending_low_priority


def test_latest_coalesced_face_position_is_applied_when_speaking_ends():
    sm = FaceStateMachine(random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/voice/wake_word"))
    sm.handle_event(Event("bmo/camera/face_position", {"x": 0.2}))
    sm.handle_event(Event("bmo/camera/face_position", {"x": 0.8}))
    assert sm.state == FaceState.THINKING
    sm.handle_event(Event("bmo/ai/speaking_start", {"amplitude": []}))
    sm.handle_event(Event("bmo/ai/speaking_end"))
    assert sm.state == FaceState.LOOK_RIGHT


def test_lower_priority_events_do_not_interrupt_alert():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/notify/event", {"priority": "high", "title": "Door"}))
    sm.handle_event(Event("bmo/system/state", {"emotion": "hot"}))
    assert sm.state == FaceState.ALERT
    now["t"] = 5.0
    sm.tick()
    assert sm.state == FaceState.HOT
