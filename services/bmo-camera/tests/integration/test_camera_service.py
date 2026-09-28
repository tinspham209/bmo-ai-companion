from queue import Queue
from time import sleep
from urllib.error import URLError

import numpy as np

from camera import CameraService
from config import CameraConfig
from detector import FaceDetection


class FakeCapture:
    def __init__(self):
        self.opened = False
        self.released = False
        self.requested_fps = []
        self.read_count = 0

    def open(self):
        self.opened = True
        return True

    def read(self):
        if self.released:
            return False, None
        self.read_count += 1
        sleep(0.001)
        return True, np.zeros((120, 160, 3), dtype=np.uint8)

    def release(self):
        self.released = True
        self.opened = False

    def reported_fps(self):
        return 30.0

    def set_requested_fps(self, fps):
        self.requested_fps.append(fps)
        return True


class FakeFaceDetector:
    def detect(self, gray):
        return [FaceDetection(0.75, 400, (100, 20, 20, 20))]


class FakeMotionDetector:
    def score(self, gray):
        return 0.0

    def reset(self):
        pass


class FakeMqtt:
    def __init__(self, face_state_queue):
        self.face_state_queue = face_state_queue
        self.events = []
        self.started = False
        self.stopped = False

    def connect(self):
        self.started = True

    def wait_connected(self, timeout):
        return True

    def publish(self, topic, payload):
        self.events.append((topic, payload))
        return True

    def stop(self):
        self.stopped = True


def test_initial_face_state_sync_applies_queued_mqtt_updates_after_http_state():
    states = Queue()
    capture = FakeCapture()
    mqtt = FakeMqtt(states)

    def face_state_fetcher(url, timeout):
        states.put("idle")
        return "sleep"

    service = CameraService(
        CameraConfig(),
        capture=capture,
        face_detector=FakeFaceDetector(),
        motion_detector=FakeMotionDetector(),
        mqtt_client=mqtt,
        face_state_queue=states,
        face_state_fetcher=face_state_fetcher,
    )

    service.start()
    assert service.status()["sleeping"] is False
    assert capture.requested_fps == []
    assert service.status()["target_processing_fps"] is None
    service.stop()


def test_frame_processing_publishes_metadata_without_frames():
    clock_value = {"now": 0.0}
    states = Queue()
    capture = FakeCapture()
    mqtt = FakeMqtt(states)
    service = CameraService(
        CameraConfig(),
        capture=capture,
        face_detector=FakeFaceDetector(),
        motion_detector=FakeMotionDetector(),
        mqtt_client=mqtt,
        face_state_fetcher=lambda url, timeout: "idle",
        now_fn=lambda: clock_value["now"],
    )

    service.start()
    service._camera_ready = True
    events = service.process_frame(
        np.zeros((120, 160, 3), dtype=np.uint8),
        now=0.0,
    )
    assert [event.topic for event in events] == [
        "bmo/camera/person_detected",
        "bmo/camera/face_position",
    ]
    status = service.status()
    assert status["presence"] == "present"
    assert status["camera_ready"] is True
    assert status["frame_width"] == 160
    assert status["frame_height"] == 120
    assert "frame" not in status and "image" not in status
    assert mqtt.events == [(event.topic, event.payload) for event in events]
    service.stop()
    assert capture.released
    assert mqtt.stopped


def test_face_state_sleep_uses_five_fps_and_wake_restores_active_rate():
    states = Queue()
    capture = FakeCapture()
    mqtt = FakeMqtt(states)
    service = CameraService(
        CameraConfig(),
        capture=capture,
        face_detector=FakeFaceDetector(),
        motion_detector=FakeMotionDetector(),
        mqtt_client=mqtt,
        face_state_queue=states,
        face_state_fetcher=lambda url, timeout: "sleep",
    )
    service.start()
    assert service.status()["sleeping"] is True
    assert service.status()["target_processing_fps"] == 5.0
    assert capture.requested_fps == [5.0]
    service.face_state_queue.put("idle")
    service._drain_face_state_updates()
    assert service.status()["sleeping"] is False
    assert capture.requested_fps == [5.0, 30.0]
    assert service.status()["target_processing_fps"] is None
    service.stop()


def test_face_state_api_failure_uses_active_rate_and_reports_warning(caplog):
    states = Queue()
    capture = FakeCapture()
    mqtt = FakeMqtt(states)

    def fail_state_lookup(url, timeout):
        raise URLError("face API unavailable")

    service = CameraService(
        CameraConfig(),
        capture=capture,
        face_detector=FakeFaceDetector(),
        motion_detector=FakeMotionDetector(),
        mqtt_client=mqtt,
        face_state_queue=states,
        face_state_fetcher=fail_state_lookup,
    )
    service.start()
    assert service.status()["sleeping"] is False
    assert capture.requested_fps == []
    assert service.status()["target_processing_fps"] is None
    assert "Could not synchronize initial face state" in caplog.text
    service.stop()


def test_status_tracks_capture_reads_separately_from_processed_frames():
    service = CameraService(
        CameraConfig(),
        capture=FakeCapture(),
        face_detector=FakeFaceDetector(),
        motion_detector=FakeMotionDetector(),
        mqtt_client=FakeMqtt(Queue()),
    )
    service._record_capture_read_fps(0.0)
    service._record_capture_read_fps(0.5)
    service._record_capture_read_fps(1.0)
    status = service.status()
    assert status["capture_read_fps"] == 2.0
    assert status["processing_fps"] == 0.0


def test_capture_worker_runs_independently_and_stops_cleanly():
    class StopAfterFrameDetector:
        service = None

        def detect(self, gray):
            self.service.request_stop()
            return []

    states = Queue()
    capture = FakeCapture()
    mqtt = FakeMqtt(states)
    detector = StopAfterFrameDetector()
    service = CameraService(
        CameraConfig(),
        capture=capture,
        face_detector=detector,
        motion_detector=FakeMotionDetector(),
        mqtt_client=mqtt,
        face_state_queue=states,
        face_state_fetcher=lambda url, timeout: "idle",
    )
    detector.service = service

    service.run()

    assert capture.read_count > 0
    assert capture.released
    assert mqtt.stopped


def test_camera_reopens_after_repeated_read_failures_and_stops_cleanly():
    class RecoveringCapture(FakeCapture):
        def __init__(self):
            super().__init__()
            self.open_count = 0

        def open(self):
            self.open_count += 1
            self.opened = True
            return True

    states = Queue()
    capture = RecoveringCapture()
    mqtt = FakeMqtt(states)
    service = CameraService(
        CameraConfig(),
        capture=capture,
        face_detector=FakeFaceDetector(),
        motion_detector=FakeMotionDetector(),
        mqtt_client=mqtt,
        face_state_queue=states,
        wait_fn=lambda delay: False,
    )
    capture.open()
    service._tracker.mark_camera_ready(now=0.0)
    service._tracker.pause_timers(now=1.0)
    service._camera_ready = True
    service._read_failures = 5
    service._recover_camera()

    assert capture.open_count == 2
    assert service.status()["camera_open"] is True
    assert service.status()["camera_ready"] is False
    service.stop()
    assert capture.released
    assert mqtt.stopped
