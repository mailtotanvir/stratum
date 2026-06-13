from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_event import EventType
from app.services.event_service import EventService
from app.services.runtime_health_service import RuntimeHealthService
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 13, 21, 0, tzinfo=UTC)


class StaticSessions:
    def __init__(self, records=None):
        self.records = records or []

    def list_sessions(self):
        return list(self.records)


class StaticReconstruction:
    def __init__(
        self,
        *,
        task_inconsistent=0,
        proposal_inconsistent=0,
    ):
        self.task_inconsistent = task_inconsistent
        self.proposal_inconsistent = proposal_inconsistent

    def task_consistency_health(self):
        return {"inconsistent": self.task_inconsistent}

    def proposal_consistency_health(self):
        return {"inconsistent": self.proposal_inconsistent}


class StaticDiagnostics:
    def __init__(
        self,
        *,
        recommendation_inconsistent=0,
        missing_snapshots=0,
    ):
        self.recommendation_inconsistent = recommendation_inconsistent
        self.missing_snapshots = missing_snapshots

    def planner_recommendation_health(self):
        return {
            "consistency": {
                "inconsistent": self.recommendation_inconsistent
            },
            "recommendations_missing_context_snapshot": (
                self.missing_snapshots
            ),
        }


def make_health_service(
    tmp_path,
    *,
    sessions=None,
    task_inconsistent=0,
    proposal_inconsistent=0,
    recommendation_inconsistent=0,
    missing_snapshots=0,
):
    events = EventService(TraceService(tmp_path / "runtime_health.db"))
    service = RuntimeHealthService(
        events=events,
        sessions=StaticSessions(sessions),
        reconstruction=StaticReconstruction(
            task_inconsistent=task_inconsistent,
            proposal_inconsistent=proposal_inconsistent,
        ),
        diagnostics=StaticDiagnostics(
            recommendation_inconsistent=recommendation_inconsistent,
            missing_snapshots=missing_snapshots,
        ),
        clock=lambda: GENERATED_AT,
    )
    return service, events


def result_by_name(health):
    return {
        result.subsystem_name: result
        for result in health.subsystem_results
    }


def test_runtime_health_is_healthy_and_deterministic(tmp_path) -> None:
    service, events = make_health_service(tmp_path)

    first = service.evaluate()
    second = service.evaluate()

    assert first == second
    assert first.overall_status == "healthy"
    assert first.health_score == 100
    assert [result.subsystem_name for result in first.subsystem_results] == [
        "runtime",
        "governance",
        "planner",
        "projections",
        "queries",
        "diagnostics",
    ]
    assert all(
        result.status == "healthy" and result.score == 100
        for result in first.subsystem_results
    )
    evaluated = events.list_persisted_events(
        event_type="runtime_health_evaluated"
    )
    assert len(evaluated) == 12
    assert evaluated[0].metadata == {
        "subsystem": "runtime",
        "status": "healthy",
        "score": 100,
    }


def test_runtime_health_reports_projection_and_query_failures(
    tmp_path,
) -> None:
    service, events = make_health_service(tmp_path)
    events.emit_event_sync(
        EventType.PROJECTION_REBUILD_FAILED,
        "Projection contract validation failed",
        severity="error",
    )
    events.emit_event_sync(
        EventType.PROJECTION_VERIFICATION_FAILED,
        "Projection verification failed",
        severity="error",
    )
    events.emit_event_sync(
        EventType.RUNTIME_QUERY_EXECUTION_FAILED,
        "Runtime query execution failed",
        severity="error",
    )
    events.emit_event_sync(
        EventType.QUERY_VERIFICATION_FAILED,
        "Incomplete query reconstruction metadata",
        severity="error",
    )

    health = service.evaluate()
    results = result_by_name(health)

    assert health.overall_status == "degraded"
    assert results["projections"].score == 45
    assert results["projections"].status == "unhealthy"
    assert results["projections"].diagnostics == {
        "rebuild_failure_count": 1,
        "verification_failure_count": 1,
        "contract_validation_failure_count": 1,
    }
    assert results["queries"].score == 45
    assert results["queries"].status == "unhealthy"
    assert results["queries"].diagnostics == {
        "verification_failure_count": 1,
        "execution_failure_count": 1,
        "reconstruction_failure_count": 1,
    }
    assert {
        finding["finding_type"]
        for finding in results["queries"].findings
    } == {
        "query_verification_failure",
        "query_execution_failure",
        "query_reconstruction_failure",
    }


def test_runtime_health_subsystem_scoring(tmp_path) -> None:
    sessions = [
        SimpleNamespace(
            status="running",
            completed_at=GENERATED_AT,
        ),
        SimpleNamespace(
            status="completed",
            completed_at=None,
        ),
    ]
    service, events = make_health_service(
        tmp_path,
        sessions=sessions,
        task_inconsistent=1,
        proposal_inconsistent=1,
        recommendation_inconsistent=1,
        missing_snapshots=2,
    )
    events.emit_event_sync(
        EventType.RUNTIME_GOVERNANCE_WARNING,
        "Governance warning",
        severity="warning",
    )

    health = service.evaluate()
    results = result_by_name(health)

    assert results["runtime"].score == 40
    assert results["runtime"].status == "unhealthy"
    assert results["planner"].score == 65
    assert results["planner"].status == "degraded"
    assert results["governance"].score == 75
    assert results["governance"].status == "warning"
    assert results["diagnostics"].score == 97
    assert results["diagnostics"].status == "healthy"


def test_runtime_health_check_failure_isolated_to_subsystem(
    tmp_path,
) -> None:
    service, events = make_health_service(tmp_path)
    service._sessions = SimpleNamespace(
        list_sessions=lambda: (_ for _ in ()).throw(
            RuntimeError("session store unavailable")
        )
    )

    health = service.evaluate()
    runtime = result_by_name(health)["runtime"]

    assert runtime.status == "unhealthy"
    assert runtime.score == 0
    assert runtime.findings[0]["finding_type"] == "health_check_failed"
    failed = events.list_persisted_events(
        event_type="runtime_health_check_failed"
    )
    assert failed[-1].metadata == {
        "subsystem": "runtime",
        "status": "unhealthy",
        "score": 0,
    }


def test_runtime_health_endpoint_is_operational() -> None:
    response = TestClient(app).get("/observability/health")

    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] in {
        "healthy",
        "warning",
        "degraded",
        "unhealthy",
    }
    assert 0 <= body["health_score"] <= 100
    assert [
        result["subsystem_name"]
        for result in body["subsystem_results"]
    ] == [
        "runtime",
        "governance",
        "planner",
        "projections",
        "queries",
        "diagnostics",
    ]
