from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.artifact_lineage import (
    ArtifactLineageChain,
    ArtifactLineageRecord,
)
from app.models.decision_lineage import (
    DecisionLineageChain,
    DecisionLineageEvidence,
    DecisionLineageEvidenceSummary,
    DecisionLineageRecord,
)
from app.models.governance_audit import GovernanceAuditRecord
from app.models.runtime_event import EventType
from app.models.runtime_health import RuntimeHealthStatusValue
from app.models.runtime_reconstruction import (
    RuntimeReconstructionHealthSummary,
    RuntimeReconstructionView,
)
from app.services.artifact_lineage_service import ArtifactLineageNotFoundError
from app.services.decision_lineage_service import DecisionLineageNotFoundError
from app.services.event_service import EventService, event_service
from app.services.explainability_service import (
    ExplainabilityService,
    ExplanationGenerationError,
    ExplanationNotFoundError,
)
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


GENERATED_AT = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class StaticDecisions:
    def __init__(self, records=None, evidence=None, malformed=False):
        self.records = records or [decision_record()]
        self.evidence = evidence or [decision_evidence()]
        self.malformed = malformed

    def get_chain(self, decision_id: str):
        if self.malformed:
            return SimpleNamespace(records=["malformed"], complete=True)
        records = [
            record for record in self.records if record.decision_id == decision_id
        ]
        if not records:
            raise DecisionLineageNotFoundError(
                f"Decision lineage not found: {decision_id}"
            )
        return DecisionLineageChain(
            decision_id=decision_id,
            records=records,
            complete=not bool(records[-1].metadata.get("orphaned")),
        )

    def evidence_summary(self, decision_id: str):
        return DecisionLineageEvidenceSummary(
            decision_id=decision_id,
            evidence_count=len(self.evidence),
            evidence=list(self.evidence),
            related_artifact_ids=["artifact-1"],
        )


class StaticArtifacts:
    def __init__(self, records=None, missing=None):
        self.records = records or [artifact_record()]
        self.missing = set(missing or [])

    def get_chain(self, artifact_id: str):
        if artifact_id in self.missing:
            raise ArtifactLineageNotFoundError(
                f"Artifact lineage not found: {artifact_id}"
            )
        record = next(
            (
                item
                for item in self.records
                if item.artifact_id == artifact_id
            ),
            None,
        )
        if record is None:
            raise ArtifactLineageNotFoundError(
                f"Artifact lineage not found: {artifact_id}"
            )
        return ArtifactLineageChain(
            artifact_id=artifact_id,
            records=[record],
            complete=record.lineage_status == "linked",
        )


class StaticGovernance:
    def __init__(self, records=None):
        self.records = records or [governance_record()]

    def list_records(self):
        return list(self.records)


class StaticReconstruction:
    def __init__(self, view=None, exc=None):
        self.view = view or reconstruction_view()
        self.exc = exc

    def reconstruct(self, session_id: str):
        if self.exc is not None:
            raise self.exc
        return self.view


def decision_record(**updates) -> DecisionLineageRecord:
    data = {
        "decision_id": "decision-1",
        "session_id": "session-1",
        "recommendation_id": "recommendation-1",
        "proposal_id": "proposal-1",
        "parent_decision_id": None,
        "lineage_depth": 1,
        "selected_at": GENERATED_AT,
        "decision_type": "tool_selection",
        "outcome": "selected",
        "evidence_count": 1,
        "source_event_ids": [1, 2],
        "related_artifact_ids": ["artifact-1"],
        "related_proposal_ids": ["proposal-1"],
        "metadata": {},
    }
    data.update(updates)
    return DecisionLineageRecord(**data)


def decision_evidence() -> DecisionLineageEvidence:
    return DecisionLineageEvidence(
        evidence_id="evidence-1",
        evidence_type="runtime_event",
        evidence_reference="event:1",
        summary="Selected recommendation had the highest confidence.",
        source_event_id=3,
    )


def artifact_record(**updates) -> ArtifactLineageRecord:
    data = {
        "artifact_id": "artifact-1",
        "artifact_path": "artifacts/report.md",
        "artifact_type": "report",
        "session_id": "session-1",
        "source_event_id": 4,
        "producing_tool_invocation_id": "tool-invocation-1",
        "proposal_id": "proposal-1",
        "decision_id": "decision-1",
        "parent_artifact_ids": [],
        "related_event_ids": [4, 5],
        "created_at": GENERATED_AT,
        "updated_at": GENERATED_AT,
        "lineage_status": "linked",
        "metadata": {},
    }
    data.update(updates)
    return ArtifactLineageRecord(**data)


def governance_record() -> GovernanceAuditRecord:
    return GovernanceAuditRecord(
        decision_id="decision-1",
        decision_type="tool_selection",
        session_id="session-1",
        source_event_id=6,
        occurred_at=GENERATED_AT,
        actor="runtime_operator",
        outcome="selected",
        evidence_count=1,
        policy_reference="runtime_governance_policy",
    )


def reconstruction_view(incomplete=False) -> RuntimeReconstructionView:
    return RuntimeReconstructionView(
        session_id="session-1",
        session_status="completed",
        started_at=GENERATED_AT,
        completed_at=GENERATED_AT,
        total_events=6,
        warnings_count=0,
        errors_count=0,
        critical_count=0,
        governance_decisions=[],
        proposal_summaries=[],
        decision_lineage_summaries=[
            {
                "decision_id": "decision-1",
                "decision_type": "tool_selection",
                "outcome": "selected",
                "occurred_at": GENERATED_AT,
                "lineage_depth": 1,
                "evidence_count": 1,
                "proposal_id": "proposal-1",
                "artifact_ids": ["artifact-1"],
            }
        ],
        artifact_lineage_summaries=[
            {
                "artifact_id": "artifact-1",
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "created_at": GENERATED_AT,
                "updated_at": GENERATED_AT,
                "lineage_status": "linked",
                "proposal_id": "proposal-1",
                "decision_id": "decision-1",
                "producing_tool_invocation_id": "tool-invocation-1",
            }
        ],
        tool_execution_summaries=[],
        health_consistency_status=RuntimeReconstructionHealthSummary(
            status="healthy",
            health_score=100,
            consistency_status="consistent",
            finding_count=0,
            incomplete_reason_count=1 if incomplete else 0,
        ),
        timeline=[],
        incomplete=incomplete,
        incomplete_reasons=(
            ["decision_lineage_incomplete:decision-1"] if incomplete else []
        ),
    )


def make_service(tmp_path, **overrides) -> tuple[ExplainabilityService, EventService]:
    events = EventService(TraceService(tmp_path / "explainability.db"))
    service = ExplainabilityService(
        decisions=overrides.get("decisions", StaticDecisions()),
        governance=overrides.get("governance", StaticGovernance()),
        artifacts=overrides.get("artifacts", StaticArtifacts()),
        reconstruction=overrides.get(
            "reconstruction",
            StaticReconstruction(),
        ),
        events=events,
        clock=lambda: GENERATED_AT,
        timer=iter([1.0, 1.025, 2.0, 2.025, 3.0, 3.025]).__next__,
    )
    return service, events


def test_decision_explanation(tmp_path) -> None:
    service, events = make_service(tmp_path)

    explanation = service.explain_decision("decision-1")

    assert explanation.decision_id == "decision-1"
    assert explanation.decision_type == "tool_selection"
    assert explanation.outcome == "selected"
    assert explanation.recommendation_source == "recommendation-1"
    assert explanation.proposal_source == "proposal-1"
    assert len(explanation.governance_actions) == 1
    assert explanation.evidence_summary[0].evidence_id == "evidence-1"
    assert explanation.related_artifacts[0].artifact_id == "artifact-1"
    assert explanation.lineage_depth == 1
    assert explanation.complete is True
    generated = events.list_persisted_events(event_type="explanation_generated")
    assert generated[-1].metadata["explanations_generated_total"] == 1


def test_artifact_explanation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    explanation = service.explain_artifact("artifact-1")

    assert explanation.artifact_id == "artifact-1"
    assert explanation.decision_id == "decision-1"
    assert explanation.proposal_id == "proposal-1"
    assert explanation.producing_tool_invocation_id == "tool-invocation-1"
    assert explanation.related_event_ids == [4, 5]
    assert explanation.complete is True


def test_session_explanation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    explanation = service.explain_session("session-1")

    assert explanation.subject_type == "session"
    assert explanation.subject_id == "session-1"
    assert [item.decision_id for item in explanation.decisions] == [
        "decision-1"
    ]
    assert [item.artifact_id for item in explanation.artifacts] == [
        "artifact-1"
    ]
    assert explanation.evidence[0].evidence_id == "evidence-1"
    assert explanation.complete is True


def test_incomplete_lineage_handling(tmp_path) -> None:
    service, events = make_service(
        tmp_path,
        decisions=StaticDecisions(
            records=[
                decision_record(
                    metadata={
                        "orphaned": True,
                        "incomplete_reasons": ["missing_parent_decision"],
                    },
                )
            ]
        ),
    )

    explanation = service.explain_decision("decision-1")

    assert explanation.complete is False
    assert explanation.incomplete_reasons == [
        "decision_lineage_incomplete",
        "missing_parent_decision",
    ]
    incomplete = events.list_persisted_events(
        event_type="explanation_incomplete"
    )
    assert incomplete[-1].metadata["incomplete_explanations_total"] == 1


def test_deterministic_explanation_generation(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    first = service.explain_decision("decision-1")
    second = service.explain_decision("decision-1")

    assert first == second


def test_missing_related_artifact_marks_decision_explanation_incomplete(
    tmp_path,
) -> None:
    service, _ = make_service(
        tmp_path,
        artifacts=StaticArtifacts(missing=["artifact-1"]),
    )

    explanation = service.explain_decision("decision-1")

    assert explanation.complete is False
    assert explanation.related_artifacts[0].lineage_status == "missing"
    assert explanation.incomplete_reasons == [
        "missing_artifact_lineage:artifact-1"
    ]


def test_malformed_lineage_data_fails_explanation(tmp_path) -> None:
    service, events = make_service(
        tmp_path,
        decisions=StaticDecisions(malformed=True),
    )

    with pytest.raises(ExplanationGenerationError):
        service.explain_decision("decision-1")

    failed = events.list_persisted_events(event_type="explanation_failed")
    assert failed[-1].metadata["error_type"] == "TypeError"
    assert failed[-1].metadata["explanation_failures_total"] == 1


def test_partial_reconstruction_marks_decision_explanation_incomplete(
    tmp_path,
) -> None:
    service, _ = make_service(
        tmp_path,
        reconstruction=StaticReconstruction(exc=RuntimeError("missing")),
    )

    explanation = service.explain_decision("decision-1")

    assert explanation.complete is False
    assert explanation.incomplete_reasons == [
        "runtime_reconstruction_unavailable"
    ]


def test_missing_decision_reference_raises_not_found(tmp_path) -> None:
    service, _ = make_service(tmp_path)

    with pytest.raises(ExplanationNotFoundError):
        service.explain_decision("missing-decision")


def seed_route_explanation_events() -> str:
    session = runtime_session_service.create_session("explain-task")
    event_service.emit_event_sync(
        EventType.PLANNER_RECOMMENDATION_CREATED,
        "Recommendation created",
        metadata={
            "recommendation_id": "route-recommendation",
            "session_id": session.id,
            "task_id": session.task_id,
            "status": "active",
            "created_at": GENERATED_AT.isoformat(),
        },
    )
    event_service.emit_event_sync(
        EventType.PROPOSAL_GENERATED,
        "Proposal generated",
        metadata={
            "proposal_id": "route-proposal",
            "source_type": "planner_recommendation",
            "source_id": "route-recommendation",
            "session_id": session.id,
            "task_id": session.task_id,
            "status": "proposed",
            "created_at": GENERATED_AT.isoformat(),
        },
    )
    event_service.emit_event_sync(
        EventType.DECISION_RECORD_CREATED,
        "Decision record created",
        metadata={
            "decision_id": "route-decision",
            "decision_type": "tool_selection",
            "selected_entity_id": "route-recommendation",
            "selected_entity_type": "planner_recommendation",
            "recommendation_id": "route-recommendation",
            "proposal_id": "route-proposal",
            "related_artifact_ids": ["route-artifact"],
            "session_id": session.id,
            "task_id": session.task_id,
            "created_at": GENERATED_AT.isoformat(),
        },
    )
    event_service.emit_event_sync(
        EventType.DECISION_EVIDENCE_CREATED,
        "Decision evidence created",
        metadata={
            "evidence_id": "route-evidence",
            "decision_id": "route-decision",
            "evidence_type": "runtime_event",
            "evidence_reference": "route-event",
            "summary": "Route evidence",
        },
    )
    event_service.emit_event_sync(
        EventType.ARTIFACT_CREATED,
        "Artifact created",
        metadata={
            "artifact_id": "route-artifact",
            "path": "artifacts/route.md",
            "kind": "report",
            "decision_id": "route-decision",
            "proposal_id": "route-proposal",
            "session_id": session.id,
            "task_id": session.task_id,
            "created_at": GENERATED_AT.isoformat(),
        },
    )
    return session.id


def test_decision_explanation_endpoint() -> None:
    seed_route_explanation_events()

    response = TestClient(app).get(
        "/runtime/explainability/decisions/route-decision"
    )

    assert response.status_code == 200
    assert response.json()["decision_id"] == "route-decision"
    assert response.json()["evidence_summary"][0]["evidence_id"] == (
        "route-evidence"
    )


def test_artifact_explanation_endpoint() -> None:
    seed_route_explanation_events()

    response = TestClient(app).get(
        "/runtime/explainability/artifacts/route-artifact"
    )

    assert response.status_code == 200
    assert response.json()["artifact_id"] == "route-artifact"
    assert response.json()["decision_id"] == "route-decision"


def test_session_explanation_endpoint() -> None:
    session_id = seed_route_explanation_events()

    response = TestClient(app).get(
        f"/runtime/explainability/sessions/{session_id}"
    )

    assert response.status_code == 200
    assert response.json()["subject_id"] == session_id
    assert response.json()["decisions"][0]["decision_id"] == "route-decision"
