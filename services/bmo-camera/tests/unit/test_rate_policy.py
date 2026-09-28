from camera import FrameRatePolicy


def test_sleep_mode_caps_analysis_and_auto_mode_restores_native_capture():
    policy = FrameRatePolicy(active_fps=None, sleep_fps=5)
    assert policy.target_fps(sleeping=True, reported_fps=30) == 5
    assert policy.target_fps(sleeping=False, reported_fps=30) is None


def test_active_auto_rate_is_uncapped_even_if_reported_fps_is_inaccurate():
    policy = FrameRatePolicy(active_fps=None, sleep_fps=5)
    assert policy.target_fps(sleeping=False, reported_fps=None) is None
    assert policy.target_fps(sleeping=False, reported_fps=15) is None


def test_explicit_active_rate_caps_camera_rate():
    policy = FrameRatePolicy(active_fps=25, sleep_fps=5)
    assert policy.target_fps(sleeping=False, reported_fps=30) == 25
    assert policy.target_fps(sleeping=False, reported_fps=15) == 25
    assert policy.target_fps(sleeping=True, reported_fps=30) == 5
