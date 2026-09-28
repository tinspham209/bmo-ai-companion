"""Camera capture, frame-rate policy, and runtime processing loop."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import platform
from queue import Empty, Queue
import signal
import threading
import time
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

import cv2
import numpy as np

from config import CameraConfig
from detector import FaceDetection, FaceDetector, MotionDetector, prepare_analysis_frame
from mqtt_client import CameraMqttClient, FACE_STATES
from state import CameraEvent, CameraEventTracker

logger = logging.getLogger(__name__)


class CameraOpenError(RuntimeError):
    """Raised when the camera cannot be opened or recovered."""


class CameraSource(Protocol):
    def open(self) -> bool: ...
    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def release(self) -> None: ...
    def reported_fps(self) -> float | None: ...
    def set_requested_fps(self, fps: float | None) -> bool: ...


class OpenCVCapture:
    def __init__(self, config: CameraConfig):
        self.config = config
        self._capture = None
        self._native_fps: float | None = None
        self._capture_lock = threading.RLock()

    def _backend_code(self) -> int:
        backend = self.config.backend
        if backend == "auto":
            if platform.system() == "Darwin":
                return cv2.CAP_AVFOUNDATION
            if hasattr(cv2, "CAP_V4L2"):
                return cv2.CAP_V4L2
            return cv2.CAP_ANY
        if backend == "avfoundation" and hasattr(cv2, "CAP_AVFOUNDATION"):
            return cv2.CAP_AVFOUNDATION
        if backend == "v4l2" and hasattr(cv2, "CAP_V4L2"):
            return cv2.CAP_V4L2
        raise CameraOpenError(f"OpenCV backend {backend!r} is not available on this platform")

    def open(self) -> bool:
        self.release()
        self._native_fps = None
        try:
            capture = cv2.VideoCapture(self.config.device_index, self._backend_code())
        except cv2.error as error:
            raise CameraOpenError(f"OpenCV failed to open camera index {self.config.device_index}") from error
        if not capture.isOpened():
            capture.release()
            raise CameraOpenError(f"Could not open camera index {self.config.device_index}")
        with self._capture_lock:
            self._capture = capture
        if self.config.active_fps is not None:
            self.set_requested_fps(float(self.config.active_fps))
        self._native_fps = self.reported_fps()
        logger.info(
            "Opened camera index %s with %s backend; reported FPS=%s",
            self.config.device_index,
            self.config.backend,
            self._native_fps,
        )
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._capture_lock:
            capture = self._capture
            if capture is None:
                return False, None
            try:
                ok, frame = capture.read()
            except cv2.error as error:
                logger.warning("OpenCV camera read failed: %s", error)
                return False, None
        if not ok or frame is None or frame.size == 0:
            return False, None
        return True, frame

    def reported_fps(self) -> float | None:
        with self._capture_lock:
            capture = self._capture
            if capture is None:
                return self._native_fps
            try:
                value = float(capture.get(cv2.CAP_PROP_FPS))
            except cv2.error as error:
                logger.warning("Could not read camera FPS: %s", error)
                return self._native_fps
        if not np.isfinite(value) or value <= 0:
            return self._native_fps
        return value

    def set_requested_fps(self, fps: float | None) -> bool:
        if fps is None:
            return False
        with self._capture_lock:
            if self._capture is None:
                return False
            try:
                return bool(self._capture.set(cv2.CAP_PROP_FPS, float(fps)))
            except cv2.error as error:
                logger.warning("OpenCV backend rejected FPS request %s: %s", fps, error)
                return False

    def release(self) -> None:
        with self._capture_lock:
            capture = self._capture
            self._capture = None
            if capture is not None:
                capture.release()


class FrameRatePolicy:
    def __init__(self, active_fps: int | None, sleep_fps: int = 5):
        self.active_fps = active_fps
        self.sleep_fps = sleep_fps

    def target_fps(self, sleeping: bool, reported_fps: float | None) -> float | None:
        if sleeping:
            return float(self.sleep_fps)
        if self.active_fps is None:
            return None
        return float(self.active_fps)


def fetch_face_state(url: str, timeout: float) -> str:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("state"), str):
        raise ValueError("face state API returned an invalid response")
    state = payload["state"].lower()
    if state not in FACE_STATES:
        raise ValueError(f"face state API returned an unknown state: {state!r}")
    return state


class CameraService:
    def __init__(
        self,
        config: CameraConfig,
        capture: CameraSource | None = None,
        face_detector: FaceDetector | None = None,
        motion_detector: MotionDetector | None = None,
        mqtt_client: CameraMqttClient | None = None,
        face_state_queue: Queue[str] | None = None,
        face_state_fetcher: Callable[[str, float], str] = fetch_face_state,
        now_fn: Callable[[], float] = time.monotonic,
        wait_fn: Callable[[float], bool] | None = None,
    ):
        self.config = config
        self.capture = capture or OpenCVCapture(config)
        self.face_detector = face_detector or FaceDetector(config.min_face_size)
        self.motion_detector = motion_detector or MotionDetector()
        self.face_state_queue = face_state_queue or Queue()
        self.mqtt = mqtt_client or CameraMqttClient(
            config.mqtt_broker,
            config.mqtt_port,
            self.face_state_queue,
        )
        self.face_state_fetcher = face_state_fetcher
        self.now_fn = now_fn
        self._stop_event = threading.Event()
        self._wait_fn = wait_fn or self._stop_event.wait
        self._lock = threading.RLock()
        self._frame_condition = threading.Condition(self._lock)
        self._latest_frame: np.ndarray | None = None
        self._frame_sequence = 0
        self._capture_thread: threading.Thread | None = None
        self._capture_error: CameraOpenError | None = None
        self._tracker = CameraEventTracker(config, now_fn=now_fn)
        self._rate_policy = FrameRatePolicy(config.active_fps, config.sleep_fps)
        self._running = False
        self._camera_open = False
        self._camera_ready = False
        self._tracker_ready = False
        self._sleeping = False
        self._stopped = False
        self._read_failures = 0
        self._read_failure_started_at: float | None = None
        self._reported_capture_fps: float | None = None
        self._native_capture_fps: float | None = None
        self._requested_capture_fps: float | None = None
        self._capture_fps_request_accepted: bool | None = None
        self._capture_fps_request_applied: bool | None = None
        self._sleep_capture_fps_requested = False
        self._capture_read_fps = 0.0
        self._capture_window_start: float | None = None
        self._capture_window_frames = 0
        self._frame_width: int | None = None
        self._frame_height: int | None = None
        self._processing_fps = 0.0
        self._fps_window_start: float | None = None
        self._fps_window_frames = 0
        self._last_processed_at: float | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self._stop_event.clear()
        if not self.capture.open():
            raise CameraOpenError(f"Could not open camera index {self.config.device_index}")
        with self._lock:
            self._camera_open = True
            self._reported_capture_fps = self.capture.reported_fps()
            self._native_capture_fps = self._reported_capture_fps
        self.mqtt.connect()
        self.mqtt.wait_connected(self.config.face_state_timeout_seconds)
        self.sync_initial_face_state()

    def sync_initial_face_state(self) -> None:
        try:
            state = self.face_state_fetcher(
                self.config.face_state_url,
                self.config.face_state_timeout_seconds,
            )
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
            logger.warning("Could not synchronize initial face state; using active camera rate: %s", error)
            state = None
        if state is not None:
            self._set_sleeping(state == "sleep", apply_fps=False)
        self._drain_face_state_updates(apply_fps=False)
        self._apply_requested_fps()

    def _drain_face_state_updates(self, apply_fps: bool = True) -> None:
        while True:
            try:
                state = self.face_state_queue.get_nowait()
            except Empty:
                break
            if state not in FACE_STATES:
                logger.warning("Ignoring unknown face state %r", state)
                continue
            self._set_sleeping(state == "sleep", apply_fps=apply_fps)

    def _set_sleeping(self, sleeping: bool, apply_fps: bool = True) -> None:
        with self._lock:
            if self._sleeping == sleeping:
                return
            self._sleeping = sleeping
        if apply_fps:
            self._apply_requested_fps()

    def _apply_requested_fps(self) -> None:
        if self.config.active_fps is None:
            if self._sleeping:
                target = float(self.config.sleep_fps)
            elif self._sleep_capture_fps_requested:
                target = self._native_capture_fps
            else:
                target = None
        else:
            target = self._rate_policy.target_fps(
                self._sleeping,
                self._native_capture_fps,
            )
        if target is None:
            with self._lock:
                self._requested_capture_fps = None
                self._capture_fps_request_accepted = None
                self._capture_fps_request_applied = None
            return

        accepted = self.capture.set_requested_fps(target)
        reported = self.capture.reported_fps()
        applied = (
            None
            if reported is None
            else accepted and abs(reported - target) <= max(1.0, target * 0.1)
        )
        with self._lock:
            self._requested_capture_fps = target
            self._capture_fps_request_accepted = accepted
            self._capture_fps_request_applied = applied
            if self._sleeping:
                self._sleep_capture_fps_requested = True
            else:
                self._sleep_capture_fps_requested = False
        if not accepted or applied is False:
            logger.warning(
                "Camera backend did not apply requested %.2f FPS (reported=%s); processing policy remains enforced",
                target,
                reported,
            )

    def process_frame(self, frame: np.ndarray, now: float | None = None) -> list[CameraEvent]:
        now = self.now_fn() if now is None else now
        analysis = prepare_analysis_frame(frame, self.config.analysis_width)
        faces = self.face_detector.detect(analysis)
        largest_face = max(faces, key=lambda face: face.area, default=None)
        motion_score = self.motion_detector.score(analysis)

        with self._lock:
            if not self._tracker_ready:
                self._tracker.mark_camera_ready(now)
                self._tracker_ready = True
            events = self._tracker.update(largest_face, motion_score, now)
            self._frame_height, self._frame_width = frame.shape[:2]
            self._record_processing_fps(now)
            self._last_processed_at = now
        for event in events:
            self.mqtt.publish(event.topic, event.payload)
        return events

    def _record_processing_fps(self, now: float) -> None:
        if self._fps_window_start is None:
            self._fps_window_start = now
            self._fps_window_frames = 1
            return
        self._fps_window_frames += 1
        elapsed = now - self._fps_window_start
        if elapsed >= 1.0:
            self._processing_fps = max(0.0, self._fps_window_frames - 1) / elapsed
            self._fps_window_start = now
            self._fps_window_frames = 1

    def _record_capture_read_fps(self, now: float) -> None:
        with self._lock:
            if self._capture_window_start is None:
                self._capture_window_start = now
                self._capture_window_frames = 1
                return
            self._capture_window_frames += 1
            elapsed = now - self._capture_window_start
            if elapsed >= 1.0:
                self._capture_read_fps = max(0.0, self._capture_window_frames - 1) / elapsed
                self._capture_window_start = now
                self._capture_window_frames = 1
                if not self._sleeping and self.config.active_fps is None:
                    measured = self._capture_read_fps
                    if measured > 0:
                        self._native_capture_fps = max(
                            self._native_capture_fps or 0.0,
                            measured,
                        )

    def _wait_for_processing_rate(self) -> None:
        target = self._rate_policy.target_fps(
            self._sleeping,
            self._native_capture_fps,
        )
        if target is None or self._last_processed_at is None:
            return
        delay = 1.0 / target - (self.now_fn() - self._last_processed_at)
        if delay > 0:
            self._wait_fn(delay)

    def _read_frame(self) -> tuple[bool, np.ndarray | None]:
        try:
            return self.capture.read()
        except cv2.error as error:
            logger.warning("OpenCV camera read failed: %s", error)
            return False, None

    def _recover_camera(self) -> None:
        logger.warning("Camera read failed repeatedly; attempting bounded reopen")
        self._set_camera_health(False, "Repeated camera read failures")
        self.capture.release()
        for attempt in range(3):
            if self._stop_event.is_set():
                return
            if attempt:
                self._wait_fn(0.25 * (2 ** (attempt - 1)))
            try:
                opened = self.capture.open()
            except CameraOpenError as error:
                logger.warning("Camera reopen attempt %s failed: %s", attempt + 1, error)
                continue
            if not opened:
                logger.warning("Camera reopen attempt %s did not open the device", attempt + 1)
                continue
            with self._lock:
                self._reported_capture_fps = self.capture.reported_fps()
                self._native_capture_fps = self._reported_capture_fps
            self._apply_requested_fps()
            self.motion_detector.reset()
            self._read_failures = 0
            with self._lock:
                self._camera_open = True
                self._camera_ready = False
                self._last_error = None
            return
        raise CameraOpenError("camera could not be reopened after three attempts")

    def _set_camera_health(self, camera_open: bool, error: str | None) -> None:
        with self._lock:
            self._camera_open = camera_open
            self._last_error = error

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            ok, frame = self._read_frame()
            now = self.now_fn()
            if not ok or frame is None:
                if self._stop_event.is_set():
                    break
                self._read_failures += 1
                if self._read_failure_started_at is None:
                    self._read_failure_started_at = now
                    if self._tracker_ready:
                        with self._lock:
                            self._tracker.pause_timers(now)
                self._set_camera_health(False, "Camera returned no frame")
                if self._read_failures >= 5:
                    try:
                        self._recover_camera()
                    except CameraOpenError as error:
                        with self._frame_condition:
                            self._capture_error = error
                            self._frame_condition.notify_all()
                        return
                else:
                    self._wait_fn(0.05)
                continue

            self._read_failures = 0
            if self._read_failure_started_at is not None:
                with self._lock:
                    self._tracker.resume_timers(now)
                self._read_failure_started_at = None
            self._record_capture_read_fps(now)
            with self._frame_condition:
                self._reported_capture_fps = self.capture.reported_fps()
                self._camera_open = True
                self._camera_ready = True
                self._last_error = None
                self._latest_frame = frame
                self._frame_sequence += 1
                self._frame_condition.notify_all()

    def run(self) -> None:
        try:
            self.start()
            self._capture_thread = threading.Thread(
                target=self._capture_loop,
                name="bmo-camera-capture",
                daemon=True,
            )
            self._capture_thread.start()
            last_sequence = 0
            while not self._stop_event.is_set():
                self._drain_face_state_updates()
                self._wait_for_processing_rate()
                if self._stop_event.is_set():
                    break
                with self._frame_condition:
                    while (
                        self._frame_sequence <= last_sequence
                        and self._capture_error is None
                        and not self._stop_event.is_set()
                    ):
                        self._frame_condition.wait(timeout=0.5)
                    if self._capture_error is not None:
                        raise self._capture_error
                    if self._stop_event.is_set():
                        break
                    frame = self._latest_frame
                    last_sequence = self._frame_sequence
                if frame is not None:
                    self.process_frame(frame, self.now_fn())
        finally:
            self.stop()

    def request_stop(self) -> None:
        self._stop_event.set()
        with self._frame_condition:
            self._frame_condition.notify_all()

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            self._running = False
        self._stop_event.set()
        with self._frame_condition:
            self._frame_condition.notify_all()
        try:
            self.capture.release()
        finally:
            try:
                capture_thread = self._capture_thread
                if capture_thread is not None and capture_thread is not threading.current_thread():
                    capture_thread.join(timeout=2.0)
                    if capture_thread.is_alive():
                        logger.error("Camera capture thread did not stop within 2 seconds")
            finally:
                try:
                    self.capture.release()
                finally:
                    self.mqtt.stop()

    def status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._tracker.snapshot(self.now_fn())
            target_fps = self._rate_policy.target_fps(
                self._sleeping,
                self._native_capture_fps,
            )
            return {
                "healthy": self._running and self._camera_open and self._camera_ready,
                "running": self._running,
                "camera_open": self._camera_open,
                "camera_ready": self._camera_ready,
                "backend": self.config.backend,
                "device_index": self.config.device_index,
                "frame_width": self._frame_width,
                "frame_height": self._frame_height,
                "sleeping": self._sleeping,
                "target_processing_fps": target_fps,
                "reported_capture_fps": self._reported_capture_fps,
                "requested_capture_fps": self._requested_capture_fps,
                "capture_fps_request_accepted": self._capture_fps_request_accepted,
                "capture_fps_request_applied": self._capture_fps_request_applied,
                "capture_read_fps": self._capture_read_fps,
                "processing_fps": self._processing_fps,
                "last_error": self._last_error,
                **snapshot,
            }


def install_signal_handlers(service: CameraService) -> None:
    def stop_service(signum, frame) -> None:  # pragma: no cover - exercised by integration smoke
        service.request_stop()

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
