from face.colors import ScaleContext
from face.components import build_face_layout


def test_scale_positive_and_proportional():
    s_small = ScaleContext(320, 240)
    s_big = ScaleContext(1920, 1080)
    assert s_small.scale(10) > 0
    assert s_big.scale(10) > s_small.scale(10)


def test_layout_builds_without_clipping():
    layout_small = build_face_layout(320, 240)
    layout_big = build_face_layout(1920, 1080)
    for rect in [layout_small.screen_rect, layout_small.left_eye_rect, layout_small.right_eye_rect, layout_small.mouth_rect]:
        assert rect[2] > 0 and rect[3] > 0
    assert layout_big.screen_rect[2] > layout_small.screen_rect[2]

