from api import create_app


def test_health_is_200_and_reports_degraded_status():
    app = create_app(lambda: {"status": "degraded"})

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.json == {"status": "degraded"}


def test_status_returns_metric_values_and_availability_without_identifiers():
    status = {
        "healthy": True,
        "status": "healthy",
        "emotion": "happy",
        "last_sample_time": "2026-09-29T00:00:00+00:00",
        "metrics": {
            "cpu": {"available": True, "percent": 12.5},
            "ram": {
                "available": True,
                "total_bytes": 800,
                "available_bytes": 400,
                "used_percent": 50.0,
            },
            "temperature": {
                "available": True,
                "celsius": 55.0,
                "source": "soc_thermal",
            },
            "disk": {"available": True, "path": "/", "free_bytes": 600_000_000},
            "wifi": {"available": True, "connected": True},
            "bluetooth": {"available": True, "present": True, "powered": True},
        },
    }
    app = create_app(lambda: status)

    response = app.test_client().get("/status")

    assert response.status_code == 200
    assert response.json == status
    serialized = str(response.json)
    assert "ssid" not in serialized.lower()
    assert "mac_address" not in serialized.lower()
    assert "paired_device_name" not in serialized.lower()
