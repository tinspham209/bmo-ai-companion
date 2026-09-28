import numpy as np

from detector import FaceDetector, MotionDetector, prepare_analysis_frame


class FakeCascade:
    def __init__(self, boxes):
        self.boxes = boxes

    def empty(self):
        return False

    def detectMultiScale(self, gray, scaleFactor, minNeighbors, minSize):
        return self.boxes


def test_prepare_analysis_frame_preserves_aspect_ratio():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    analysis = prepare_analysis_frame(frame, analysis_width=320)
    assert analysis.shape == (180, 320)


def test_prepare_analysis_frame_rejects_empty_or_invalid_frames():
    for frame in (None, np.zeros((0, 0, 3), dtype=np.uint8), np.zeros((3,), dtype=np.uint8)):
        try:
            prepare_analysis_frame(frame, analysis_width=320)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid frame should be rejected")


def test_face_detector_returns_normalized_centers_and_areas():
    detector = FaceDetector(min_face_size=10, classifier=FakeCascade([(10, 10, 20, 20), (80, 20, 40, 30)]))
    detections = detector.detect(np.zeros((100, 200), dtype=np.uint8))
    assert [face.x_center for face in detections] == [0.1, 0.5]
    assert [face.area for face in detections] == [400, 1200]


def test_bundled_face_cascade_loads():
    detector = FaceDetector()
    assert not detector.classifier.empty()


def test_face_detector_rejects_invalid_cascade():
    class EmptyCascade(FakeCascade):
        def empty(self):
            return True

    try:
        FaceDetector(classifier=EmptyCascade([]))
    except RuntimeError as error:
        assert "cascade" in str(error).lower()
    else:
        raise AssertionError("empty cascade should fail explicitly")


def test_motion_detector_scores_changed_pixels_and_resets():
    detector = MotionDetector(pixel_threshold=25)
    still = np.zeros((100, 100), dtype=np.uint8)
    assert detector.score(still) == 0.0
    assert detector.score(still) == 0.0

    moved = still.copy()
    moved[30:70, 30:70] = 255
    score = detector.score(moved)
    assert 0.02 < score < 1.0

    detector.reset()
    assert detector.score(still) == 0.0
