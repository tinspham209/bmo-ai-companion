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

