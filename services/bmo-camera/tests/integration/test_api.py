from api import create_app


def test_health_and_status_are_local_metadata_only():
    status = {
        "healthy": True,
        "camera_open": True,
        "camera_ready": True,
        "presence": "present",
        "motion": "no_motion",
        "processing_fps": 29.5,
    }
    app = create_app(lambda: status)
    client = app.test_client()

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json == {"status": "ok"}

    result = client.get("/status")
    assert result.status_code == 200
    assert result.json == status
    assert not any("frame" in key or "image" in key for key in result.json)


def test_health_reports_camera_failure():
    app = create_app(lambda: {"healthy": False, "camera_open": False})
    response = app.test_client().get("/health")
    assert response.status_code == 503
    assert response.json == {"status": "unhealthy"}
