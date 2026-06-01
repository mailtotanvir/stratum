from app.main import app, health


def test_health() -> None:
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert health() == {"status": "ok", "service": "stratum-backend"}
