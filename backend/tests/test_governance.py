import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.runtime_event import EventType, Severity
from app.routes import diagnostics as diagnostics_routes
from app.routes import governance as governance_routes
from app.services.diagnostics_service import DiagnosticsService
from app.services.event_service import EventService, event_service
from app.services.governance_service import GovernanceService
from app.services.trace_service import TraceService


def test_default_emitted_event_severity_is_info(tmp_path) -> None:
    async def run_flow() -> None:
        store = TraceService(tmp_path / "trace.db")
        events = EventService(store)

        event = await events.emit_event(EventType.TASK_CREATED, "Created")

        assert event.severity == Severity.INFO
        assert store.list_events()[0].severity == Severity.INFO

    asyncio.run(run_flow())


def test_explicit_warning_severity_persists(tmp_path) -> None:
    async def run_flow() -> None:
        store = TraceService(tmp_path / "trace.db")
        events = EventService(store)

        await events.emit_event(
            EventType.WARNING,
            "Warning",
            severity=Severity.WARNING,
        )

        assert store.list_events()[0].severity == Severity.WARNING

    asyncio.run(run_flow())


def test_explicit_error_severity_persists(tmp_path) -> None:
    async def run_flow() -> None:
        store = TraceService(tmp_path / "trace.db")
        events = EventService(store)

        await events.emit_event(EventType.ERROR, "Error", severity="error")

        assert store.list_events()[0].severity == Severity.ERROR

    asyncio.run(run_flow())


def test_explicit_critical_severity_persists(tmp_path) -> None:
    async def run_flow() -> None:
        store = TraceService(tmp_path / "trace.db")
        events = EventService(store)

        await events.emit_event(
            EventType.ERROR,
            "Critical",
            severity=Severity.CRITICAL,
        )

        assert store.list_events()[0].severity == Severity.CRITICAL

    asyncio.run(run_flow())


def test_invalid_severity_is_rejected(tmp_path) -> None:
    async def run_flow() -> None:
        events = EventService(TraceService(tmp_path / "trace.db"))

        with pytest.raises(ValidationError):
            await events.emit_event(
                EventType.ERROR,
                "Invalid",
                severity="fatal",
            )

    asyncio.run(run_flow())


def test_governance_diagnostics_return_correct_counts(tmp_path, monkeypatch) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))
    monkeypatch.setattr(diagnostics_routes, "diagnostics_service", diagnostics)

    events.emit_event_sync(EventType.TASK_CREATED, "Created")
    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")
    events.emit_event_sync(EventType.ERROR, "Error", severity="error")
    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")
    client = TestClient(app)

    response = client.get("/diagnostics/governance")

    assert response.status_code == 200
    assert response.json() == {
        "severity_counts": {
            "info": 1,
            "warning": 1,
            "error": 1,
            "critical": 1,
        },
        "highest_severity": "critical",
        "has_critical": True,
        "status": "critical",
        "error_budget": {
            "status": "budget_exhausted",
            "exhausted": {
                "warnings": False,
                "errors": False,
                "criticals": True,
            },
        },
        "total_governance_events": 4,
    }


def test_highest_severity_is_calculated_correctly(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    events.emit_event_sync(EventType.TASK_CREATED, "Created")
    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")
    events.emit_event_sync(EventType.ERROR, "Error", severity="error")

    assert diagnostics.governance_health()["highest_severity"] == "error"
    assert diagnostics.governance_health()["has_critical"] is False


def test_governance_status_no_events_is_ok(tmp_path) -> None:
    diagnostics = DiagnosticsService(
        EventService(TraceService(tmp_path / "trace.db"))
    )

    assert diagnostics.governance_health()["status"] == "ok"


def test_governance_status_only_info_is_ok(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    events.emit_event_sync(EventType.TASK_CREATED, "Created")

    assert diagnostics.governance_health()["status"] == "ok"


def test_governance_status_warning_is_degraded(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")

    assert diagnostics.governance_health()["status"] == "degraded"


def test_governance_status_error_is_degraded(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Error", severity="error")

    assert diagnostics.governance_health()["status"] == "degraded"


def test_governance_status_critical_is_critical(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    assert diagnostics.governance_health()["status"] == "critical"


def test_governance_diagnostics_includes_error_budget(tmp_path) -> None:
    diagnostics = DiagnosticsService(
        EventService(TraceService(tmp_path / "trace.db"))
    )

    assert diagnostics.governance_health()["error_budget"] == {
        "status": "within_budget",
        "exhausted": {
            "warnings": False,
            "errors": False,
            "criticals": False,
        },
    }


def test_governance_diagnostics_error_budget_within_policy(
    tmp_path,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    for index in range(5):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    assert diagnostics.governance_health()["error_budget"] == {
        "status": "within_budget",
        "exhausted": {
            "warnings": False,
            "errors": False,
            "criticals": False,
        },
    }


def test_governance_diagnostics_error_budget_exhausted_flags(
    tmp_path,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    diagnostics = DiagnosticsService(EventService(trace_store))

    for index in range(6):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )
    for index in range(3):
        events.emit_event_sync(
            EventType.ERROR,
            f"Error {index}",
            severity="error",
        )
    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    assert diagnostics.governance_health()["error_budget"] == {
        "status": "budget_exhausted",
        "exhausted": {
            "warnings": True,
            "errors": True,
            "criticals": True,
        },
    }


def test_error_budget_empty_event_store_is_within_budget(tmp_path) -> None:
    service = GovernanceService(EventService(TraceService(tmp_path / "trace.db")))

    assert service.evaluate_error_budget() == {
        "policy": {
            "warning_budget": 5,
            "error_budget": 2,
            "critical_budget": 0,
        },
        "usage": {
            "warnings": 0,
            "errors": 0,
            "criticals": 0,
        },
        "remaining": {
            "warnings": 5,
            "errors": 2,
            "criticals": 0,
        },
        "exhausted": {
            "warnings": False,
            "errors": False,
            "criticals": False,
        },
        "status": "within_budget",
    }


def test_error_budget_warnings_within_budget(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    for index in range(5):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    budget = service.evaluate_error_budget()
    assert budget["usage"]["warnings"] == 5
    assert budget["remaining"]["warnings"] == 0
    assert budget["exhausted"]["warnings"] is False
    assert budget["status"] == "within_budget"


def test_error_budget_warnings_over_budget_exhausts_warning_budget(
    tmp_path,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    for index in range(6):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    budget = service.evaluate_error_budget()
    assert budget["usage"]["warnings"] == 6
    assert budget["remaining"]["warnings"] == -1
    assert budget["exhausted"]["warnings"] is True
    assert budget["status"] == "budget_exhausted"


def test_error_budget_errors_over_budget_exhausts_error_budget(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    for index in range(3):
        events.emit_event_sync(
            EventType.ERROR,
            f"Error {index}",
            severity="error",
        )

    budget = service.evaluate_error_budget()
    assert budget["usage"]["errors"] == 3
    assert budget["remaining"]["errors"] == -1
    assert budget["exhausted"]["errors"] is True
    assert budget["status"] == "budget_exhausted"


def test_error_budget_one_critical_exhausts_critical_budget(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    budget = service.evaluate_error_budget()
    assert budget["usage"]["criticals"] == 1
    assert budget["remaining"]["criticals"] == -1
    assert budget["exhausted"]["criticals"] is True
    assert budget["status"] == "budget_exhausted"


def test_error_budget_remaining_can_be_negative(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    for index in range(7):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    assert service.evaluate_error_budget()["remaining"]["warnings"] == -2


def test_error_budget_endpoint_response_shape_is_deterministic(
    tmp_path,
    monkeypatch,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))
    monkeypatch.setattr(governance_routes, "governance_service", service)

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")
    client = TestClient(app)

    response = client.get("/governance/error-budget")

    assert response.status_code == 200
    assert response.json() == {
        "policy": {
            "warning_budget": 5,
            "error_budget": 2,
            "critical_budget": 0,
        },
        "usage": {
            "warnings": 1,
            "errors": 0,
            "criticals": 0,
        },
        "remaining": {
            "warnings": 4,
            "errors": 2,
            "criticals": 0,
        },
        "exhausted": {
            "warnings": False,
            "errors": False,
            "criticals": False,
        },
        "status": "within_budget",
    }


def test_decision_preview_empty_event_store_allows(tmp_path) -> None:
    service = GovernanceService(EventService(TraceService(tmp_path / "trace.db")))

    assert service.preview_decision() == {
        "decision": "allow",
        "reasons": ["within_governance_policy"],
        "governance_status": "ok",
        "error_budget_status": "within_budget",
        "has_critical": False,
    }


def test_decision_preview_only_info_events_allows(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.TASK_CREATED, "Created")

    assert service.preview_decision() == {
        "decision": "allow",
        "reasons": ["within_governance_policy"],
        "governance_status": "ok",
        "error_budget_status": "within_budget",
        "has_critical": False,
    }


def test_decision_preview_warning_within_budget_warns(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")

    assert service.preview_decision() == {
        "decision": "warn",
        "reasons": ["governance_degraded"],
        "governance_status": "degraded",
        "error_budget_status": "within_budget",
        "has_critical": False,
    }


def test_decision_preview_error_within_budget_warns(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Error", severity="error")

    assert service.preview_decision() == {
        "decision": "warn",
        "reasons": ["governance_degraded"],
        "governance_status": "degraded",
        "error_budget_status": "within_budget",
        "has_critical": False,
    }


def test_decision_preview_warning_over_budget_blocks(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    for index in range(6):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    assert service.preview_decision() == {
        "decision": "block",
        "reasons": ["error_budget_exhausted"],
        "governance_status": "degraded",
        "error_budget_status": "budget_exhausted",
        "has_critical": False,
    }


def test_decision_preview_critical_event_blocks(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    assert service.preview_decision() == {
        "decision": "block",
        "reasons": ["critical_event_present", "error_budget_exhausted"],
        "governance_status": "critical",
        "error_budget_status": "budget_exhausted",
        "has_critical": True,
    }


def test_decision_preview_block_can_include_multiple_reasons(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    preview = service.preview_decision()

    assert preview["decision"] == "block"
    assert preview["reasons"] == [
        "critical_event_present",
        "error_budget_exhausted",
    ]


def test_decision_preview_endpoint_response_shape_is_deterministic(
    tmp_path,
    monkeypatch,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))
    monkeypatch.setattr(governance_routes, "governance_service", service)

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")
    client = TestClient(app)

    response = client.get("/governance/decision-preview")

    assert response.status_code == 200
    assert response.json() == {
        "decision": "warn",
        "reasons": ["governance_degraded"],
        "governance_status": "degraded",
        "error_budget_status": "within_budget",
        "has_critical": False,
    }


def test_reflection_preview_empty_event_store_not_recommended(tmp_path) -> None:
    service = GovernanceService(EventService(TraceService(tmp_path / "trace.db")))

    assert service.preview_reflection() == {
        "recommended": False,
        "reasons": ["no_reflection_needed"],
        "decision_preview": {
            "decision": "allow",
            "reasons": ["within_governance_policy"],
        },
        "governance_status": "ok",
        "error_budget_status": "within_budget",
    }


def test_reflection_preview_only_info_not_recommended(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.TASK_CREATED, "Created")

    assert service.preview_reflection() == {
        "recommended": False,
        "reasons": ["no_reflection_needed"],
        "decision_preview": {
            "decision": "allow",
            "reasons": ["within_governance_policy"],
        },
        "governance_status": "ok",
        "error_budget_status": "within_budget",
    }


def test_reflection_preview_warning_within_budget_recommended(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")

    assert service.preview_reflection() == {
        "recommended": True,
        "reasons": ["governance_degraded", "decision_preview_not_allow"],
        "decision_preview": {
            "decision": "warn",
            "reasons": ["governance_degraded"],
        },
        "governance_status": "degraded",
        "error_budget_status": "within_budget",
    }


def test_reflection_preview_error_within_budget_recommended(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Error", severity="error")

    assert service.preview_reflection() == {
        "recommended": True,
        "reasons": ["governance_degraded", "decision_preview_not_allow"],
        "decision_preview": {
            "decision": "warn",
            "reasons": ["governance_degraded"],
        },
        "governance_status": "degraded",
        "error_budget_status": "within_budget",
    }


def test_reflection_preview_budget_exhausted_recommended(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    for index in range(6):
        events.emit_event_sync(
            EventType.WARNING,
            f"Warning {index}",
            severity="warning",
        )

    assert service.preview_reflection() == {
        "recommended": True,
        "reasons": [
            "governance_degraded",
            "error_budget_exhausted",
            "decision_preview_not_allow",
        ],
        "decision_preview": {
            "decision": "block",
            "reasons": ["error_budget_exhausted"],
        },
        "governance_status": "degraded",
        "error_budget_status": "budget_exhausted",
    }


def test_reflection_preview_critical_recommended(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    assert service.preview_reflection() == {
        "recommended": True,
        "reasons": [
            "governance_critical",
            "error_budget_exhausted",
            "decision_preview_not_allow",
        ],
        "decision_preview": {
            "decision": "block",
            "reasons": ["critical_event_present", "error_budget_exhausted"],
        },
        "governance_status": "critical",
        "error_budget_status": "budget_exhausted",
    }


def test_reflection_preview_reasons_are_deterministic(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))

    events.emit_event_sync(EventType.ERROR, "Critical", severity="critical")

    assert service.preview_reflection()["reasons"] == [
        "governance_critical",
        "error_budget_exhausted",
        "decision_preview_not_allow",
    ]


def test_reflection_preview_endpoint_response_shape_is_stable(
    tmp_path,
    monkeypatch,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = GovernanceService(EventService(trace_store))
    monkeypatch.setattr(governance_routes, "governance_service", service)

    events.emit_event_sync(EventType.WARNING, "Warning", severity="warning")
    client = TestClient(app)

    response = client.get("/governance/reflection-preview")

    assert response.status_code == 200
    assert response.json() == {
        "recommended": True,
        "reasons": ["governance_degraded", "decision_preview_not_allow"],
        "decision_preview": {
            "decision": "warn",
            "reasons": ["governance_degraded"],
        },
        "governance_status": "degraded",
        "error_budget_status": "within_budget",
    }


def test_trace_behavior_still_works() -> None:
    async def run_flow() -> None:
        event = await event_service.emit_event(
            EventType.TASK_CREATED,
            "Created",
            metadata={"task_id": "task-1"},
        )
        client = TestClient(app)

        response = client.get("/trace", params={"task_id": "task-1"})

        assert response.status_code == 200
        assert response.json() == [event.to_dict()]

    asyncio.run(run_flow())
