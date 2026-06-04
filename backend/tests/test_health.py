import pytest
from fastapi.testclient import TestClient

from app.main import app, health


def test_health() -> None:
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/diagnostics/events" in paths
    assert "/diagnostics/governance" in paths
    assert "/governance/error-budget" in paths
    assert "/governance/decision-preview" in paths
    assert "/governance/reflection-preview" in paths
    assert health() == {"status": "ok", "service": "stratum-backend"}


@pytest.mark.parametrize(
    ("path", "expected_fields"),
    [
        (
            "/governance/error-budget",
            {"policy", "usage", "remaining", "exhausted", "status"},
        ),
        (
            "/governance/decision-preview",
            {
                "decision",
                "reasons",
                "governance_status",
                "error_budget_status",
                "has_critical",
            },
        ),
        (
            "/governance/reflection-preview",
            {
                "recommended",
                "reasons",
                "decision_preview",
                "governance_status",
                "error_budget_status",
            },
        ),
        (
            "/diagnostics/governance",
            {
                "severity_counts",
                "highest_severity",
                "has_critical",
                "status",
                "error_budget",
                "total_governance_events",
            },
        ),
    ],
)
def test_governance_routes_are_reachable(
    path: str,
    expected_fields: set[str],
) -> None:
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 200
    assert expected_fields <= set(response.json())
