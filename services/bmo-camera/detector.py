"""Local frame preparation and OpenCV face/motion detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class FaceDetection:
    x_center: float
    area: int
    box: tuple[int, int, int, int]


def prepare_analysis_frame(frame: np.ndarray, analysis_width: int) -> np.ndarray:
    if not isinstance(frame, np.ndarray) or frame.size == 0 or frame.ndim not in (2, 3):
        raise ValueError("camera returned an empty or invalid frame")
    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("camera returned an empty frame")
    if analysis_width < 1:
        raise ValueError("analysis_width must be > 0")

    if width > analysis_width:
        scale = analysis_width / width
        target_size = (analysis_width, max(1, int(round(height * scale))))
        frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)

    if frame.ndim == 2:
        return frame
    if frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    raise ValueError("camera frame must have 1, 3, or 4 color channels")


class FaceDetector:
    def __init__(
        self,
        min_face_size: int = 24,
        classifier=None,
        cascade_path: str | Path | None = None,
    ):
        if min_face_size < 1:
            raise ValueError("min_face_size must be > 0")
        self.min_face_size = min_face_size
        if classifier is None:
            path = Path(cascade_path) if cascade_path else Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            classifier = cv2.CascadeClassifier(str(path))
        if classifier.empty():
            raise RuntimeError("OpenCV face-detection cascade could not be loaded")
        self.classifier = classifier

    def detect(self, gray: np.ndarray) -> list[FaceDetection]:
        if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.size == 0:
            raise ValueError("face detector requires a non-empty grayscale image")
        height, width = gray.shape
        boxes = self.classifier.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(self.min_face_size, self.min_face_size),
        )
        detections = []
        for x, y, box_width, box_height in boxes:
            if box_width <= 0 or box_height <= 0:
                continue
            center_x = max(0.0, min(1.0, (float(x) + box_width / 2.0) / width))
            detections.append(
                FaceDetection(
                    x_center=center_x,
                    area=int(box_width * box_height),
                    box=(int(x), int(y), int(box_width), int(box_height)),
                )
            )
        return detections


class MotionDetector:
    def __init__(self, pixel_threshold: int = 25):
        if not 0 <= pixel_threshold <= 255:
            raise ValueError("pixel_threshold must be between 0 and 255")
        self.pixel_threshold = pixel_threshold
        self._previous: np.ndarray | None = None

    def reset(self) -> None:
        self._previous = None

    def score(self, gray: np.ndarray) -> float:
        if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.size == 0:
            raise ValueError("motion detector requires a non-empty grayscale image")
        current = cv2.GaussianBlur(gray, (5, 5), 0)
        previous = self._previous
        self._previous = current.copy()
        if previous is None or previous.shape != current.shape:
            return 0.0
        difference = cv2.absdiff(previous, current)
        _, changed = cv2.threshold(
            difference,
            self.pixel_threshold,
            255,
            cv2.THRESH_BINARY,
        )
        return float(cv2.countNonZero(changed)) / float(changed.size)
