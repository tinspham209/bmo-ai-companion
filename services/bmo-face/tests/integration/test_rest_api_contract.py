from renderer import FaceRuntime
from api import create_app


def test_health_and_state_and_validation():
    runtime = FaceRuntime(fps_target=30, fps_fallback=24, sleep_timeout_seconds=300)
    app = create_app(runtime.event_queue, runtime.current_state)
    client = app.test_client()

    health = client.get("/health")
    assert health.status_code == 200

    state = client.get("/state")
    assert state.status_code == 200
    assert state.json["state"] == "boot"

    bad = client.post("/state", json={"state": "not-real"})
    assert bad.status_code == 400

    good = client.post("/state", json={"state": "idle"})
    assert good.status_code == 200

    bad_brightness = client.post("/brightness", json={"level": 2})
    assert bad_brightness.status_code == 400

    bad_body = client.post("/state", json=["idle"])
    assert bad_body.status_code == 400

    bool_brightness = client.post("/brightness", json={"level": True})
    assert bool_brightness.status_code == 400
