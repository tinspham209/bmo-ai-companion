from renderer import FaceRuntime


def test_runtime_uses_fallback_after_sustained_low_fps():
    runtime = FaceRuntime(fps_target=30, fps_fallback=24, sleep_timeout_seconds=300)
    runtime.update_fps_policy(20, now=0.0)
    runtime.update_fps_policy(20, now=1.9)
    assert runtime.current_fps == 30
    runtime.update_fps_policy(20, now=2.0)
    assert runtime.current_fps == 24


def test_runtime_cancels_fallback_when_fps_recovers():
    runtime = FaceRuntime(fps_target=30, fps_fallback=24, sleep_timeout_seconds=300)
    runtime.update_fps_policy(20, now=0.0)
    runtime.update_fps_policy(30, now=1.0)
    runtime.update_fps_policy(20, now=1.5)
    runtime.update_fps_policy(20, now=3.4)
    assert runtime.current_fps == 30
