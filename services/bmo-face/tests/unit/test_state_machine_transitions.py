from face.state_machine import Event, FaceState, FaceStateMachine


def test_boot_to_idle_and_ready_publish():
    t = {"now": 0.0}
    sm = FaceStateMachine(now_fn=lambda: t["now"], random_fn=lambda a, b: 3.0)
    sm.transition_boot_complete()
    assert sm.state == FaceState.IDLE
    published = list(sm.publish_queue)
    assert any(x["topic"] == "bmo/face/ready" for x in published)


def test_sleep_timer_and_cancel():
    now = {"t": 0.0}
    sm = FaceStateMachine(sleep_timeout_seconds=5, now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/camera/person_left", {}))
    now["t"] += 4.9
    sm.tick()
    assert sm.state == FaceState.IDLE
    sm.handle_event(Event("bmo/camera/person_detected", {}))
    now["t"] += 1.0
    sm.tick()
    assert sm.state == FaceState.IDLE


def test_face_position_transitions():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/camera/face_position", {"x": 0.2}))
    assert sm.state == FaceState.LOOK_LEFT
    sm.handle_event(Event("bmo/camera/face_position", {"x": 0.8}))
    assert sm.state == FaceState.LOOK_RIGHT
    now["t"] += 0.6
    sm.tick()
    assert sm.state == FaceState.IDLE


def test_boot_sequence_completes_after_timeline():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    now["t"] = 1.3
    sm.tick()
    assert sm.state == FaceState.IDLE
    assert any(item["topic"] == "bmo/face/ready" for item in sm.publish_queue)


def test_listening_expires_after_ten_seconds():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/voice/listening_start"))
    assert sm.state == FaceState.LISTENING
    now["t"] = 9.9
    sm.tick()
    assert sm.state == FaceState.LISTENING
    now["t"] = 10.0
    sm.tick()
    assert sm.state == FaceState.IDLE


def test_sleep_deadline_does_not_interrupt_speaking():
    now = {"t": 0.0}
    sm = FaceStateMachine(sleep_timeout_seconds=5, now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/camera/person_left"))
    sm.handle_event(Event("bmo/ai/speaking_start", {"amplitude": []}))
    now["t"] = 5.0
    sm.tick()
    assert sm.state == FaceState.SPEAKING
    sm.handle_event(Event("bmo/ai/speaking_end"))
    sm.tick()
    assert sm.state == FaceState.SLEEP


def test_sleep_deadline_does_not_interrupt_thinking():
    now = {"t": 0.0}
    sm = FaceStateMachine(sleep_timeout_seconds=1, now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/camera/person_left"))
    sm.handle_event(Event("bmo/voice/wake_word"))
    now["t"] = 1.0
    sm.tick()
    assert sm.state == FaceState.THINKING


def test_direct_speaking_state_has_safety_timeout():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 4.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/face/set_state", {"state": "speaking"}))
    assert sm.state == FaceState.SPEAKING
    now["t"] = 15.0
    sm.tick()
    assert sm.state == FaceState.IDLE


def test_blink_animates_as_independent_overlay():
    now = {"t": 0.0}
    sm = FaceStateMachine(now_fn=lambda: now["t"], random_fn=lambda a, b: 3.0)
    sm.transition_boot_complete()
    sm.handle_event(Event("bmo/face/set_state", {"state": "happy"}))
    now["t"] = 3.0
    sm.tick()
    assert sm.blink_active
    now["t"] = 3.075
    assert sm.blink_eye_scale < 0.2
    now["t"] = 3.2
    sm.tick()
    assert not sm.blink_active
    assert sm.state == FaceState.HAPPY
