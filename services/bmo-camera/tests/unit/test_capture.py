import cv2
import pytest

import camera
from camera import CameraOpenError, OpenCVCapture
from config import CameraConfig


class FakeVideoCapture:
    def __init__(self, index, backend, opened=True, fps=30.0):
        self.index = index
        self.backend = backend
        self.opened = opened
        self.fps = fps
        self.released = False
        self.fps_requests = []

    def isOpened(self):
        return self.opened

    def get(self, property_id):
        return self.fps

    def set(self, property_id, value):
        self.fps_requests.append(value)
        self.fps = value
        return True

    def read(self):
        return True, object()

    def release(self):
        self.released = True


def test_auto_backend_uses_avfoundation_on_macos(monkeypatch):
    created = []
    monkeypatch.setattr(camera.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(cv2, "VideoCapture", lambda index, backend: created.append((index, backend)) or FakeVideoCapture(index, backend))

    capture = OpenCVCapture(CameraConfig(backend="auto"))
    assert capture.open()
    assert created == [(0, cv2.CAP_AVFOUNDATION)]
    assert capture.reported_fps() == 30.0
    capture.release()


def test_capture_requests_configured_active_fps(monkeypatch):
    handles = []

    def create(index, backend):
        handle = FakeVideoCapture(index, backend)
        handles.append(handle)
        return handle

    monkeypatch.setattr(cv2, "VideoCapture", create)
    capture = OpenCVCapture(CameraConfig(active_fps=24))
    capture.open()
    assert handles[0].fps_requests == [24]
    capture.release()
    assert handles[0].released


def test_capture_open_failure_is_explicit(monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", lambda index, backend: FakeVideoCapture(index, backend, opened=False))
    with pytest.raises(CameraOpenError, match="Could not open"):
        OpenCVCapture(CameraConfig()).open()
