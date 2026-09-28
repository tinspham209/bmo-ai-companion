from config import CameraConfig
from detector import FaceDetection
from state import CameraEventTracker


def topics(events):
    return [event.topic for event in events]


def test_initial_absence_emits_person_left_after_ten_seconds(clock):
    tracker = CameraEventTracker(CameraConfig(), now_fn=clock.now)
    assert tracker.update(None, 0.0) == []
    clock.set(9.999)
    assert tracker.update(None, 0.0) == []
    clock.set(10.0)
    events = tracker.update(None, 0.0)
    assert topics(events) == ["bmo/camera/person_left"]
    assert tracker.presence_state == "absent"
    assert tracker.motion_state == "unknown"
    clock.set(29.999)
    assert tracker.update(None, 0.0) == []
    clock.set(30.0)
    assert topics(tracker.update(None, 0.0)) == ["bmo/camera/no_motion"]


def test_detection_and_departure_are_emitted_once(clock):
    tracker = CameraEventTracker(CameraConfig(), now_fn=clock.now)
    face = FaceDetection(x_center=0.25, area=900, box=(10, 10, 30, 30))
    first = tracker.update(face, 0.0)
    assert topics(first) == ["bmo/camera/person_detected", "bmo/camera/face_position"]
    assert first[1].payload == {"x": 0.25}

    clock.advance(1.0)
    assert topics(tracker.update(face, 0.0)) == ["bmo/camera/face_position"]
    clock.advance(1.0)
    tracker.update(None, 0.0)
    clock.advance(9.999)
    assert "bmo/camera/person_left" not in topics(tracker.update(None, 0.0))
    clock.advance(0.001)
    events = tracker.update(None, 0.0)
    assert topics(events) == ["bmo/camera/person_left"]


def test_face_return_before_absence_timeout_cancels_departure(clock):
    tracker = CameraEventTracker(CameraConfig(), now_fn=clock.now)
    face = FaceDetection(x_center=0.7, area=500, box=(100, 20, 20, 25))
    tracker.update(face, 0.0)
    tracker.update(None, 0.0)
    clock.advance(9.9)
    returned = tracker.update(face, 0.0)
    assert topics(returned) == ["bmo/camera/face_position"]
    clock.advance(10.0)
    assert "bmo/camera/person_left" not in topics(tracker.update(face, 0.0))


def test_face_position_heartbeats_and_rate_limit(clock):
    config = CameraConfig()
    tracker = CameraEventTracker(config, now_fn=clock.now)
    face = FaceDetection(x_center=0.2, area=100, box=(0, 0, 10, 10))
    first = tracker.update(face, 0.0)
    assert "bmo/camera/face_position" in topics(first)
    clock.set(0.1)
    assert "bmo/camera/face_position" not in topics(tracker.update(face, 0.0))
    clock.set(0.2)
    moved = tracker.update(FaceDetection(0.3, 100, (0, 0, 10, 10)), 0.0)
    assert [event.payload for event in moved if event.topic == "bmo/camera/face_position"] == [{"x": 0.3}]
    clock.set(0.6)
    heartbeat = tracker.update(FaceDetection(0.3, 100, (0, 0, 10, 10)), 0.0)
    assert [event.payload for event in heartbeat if event.topic == "bmo/camera/face_position"] == [{"x": 0.3}]


def test_motion_and_no_motion_emit_only_on_transitions(clock):
    tracker = CameraEventTracker(CameraConfig(), now_fn=clock.now)
    face = FaceDetection(x_center=0.5, area=100, box=(0, 0, 10, 10))
    def motion_topics(events):
        return [event.topic for event in events if event.topic in {
            "bmo/camera/motion",
            "bmo/camera/no_motion",
        }]

    tracker.update(face, 0.02)
    assert motion_topics(tracker.update(face, 0.02)) == ["bmo/camera/motion"]
    clock.advance(1.0)
    assert motion_topics(tracker.update(face, 0.02)) == []
    tracker.update(face, 0.0)
    clock.advance(29.999)
    assert motion_topics(tracker.update(face, 0.0)) == []
    clock.advance(0.001)
    assert motion_topics(tracker.update(face, 0.0)) == ["bmo/camera/no_motion"]
    assert motion_topics(tracker.update(face, 0.0)) == []


def test_capture_outage_pauses_absence_and_motion_timers(clock):
    tracker = CameraEventTracker(CameraConfig(), now_fn=clock.now)
    tracker.mark_camera_ready()
    tracker.update(None, 0.0)
    clock.advance(8.0)
    tracker.pause_timers()
    clock.advance(60.0)
    tracker.resume_timers()
    assert topics(tracker.update(None, 0.0)) == []
    clock.advance(1.999)
    assert "bmo/camera/person_left" not in topics(tracker.update(None, 0.0))
    clock.advance(0.001)
    assert "bmo/camera/person_left" in topics(tracker.update(None, 0.0))
