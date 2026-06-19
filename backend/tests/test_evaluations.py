from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.schema import DecisionRecordRecord
from app.main import app
from app.models.runtime_event import EventType
from app.services.artifact_service import ArtifactService
from app.services.decision_record_service import DecisionRecordService
from app.services.event_service import EventService, event_service
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.services.reconstruction_service import ReconstructionService
from app.services.runtime_reconstruction_service import RuntimeReconstructionService
from app.services.runtime_session_service import RuntimeSessionService
from app.services.artifact_service import artifact_service
from app.services.runtime_session_service import runtime_session_service
from app.services.trace_service import TraceService


def test_evaluation_creation_persists_and_emits_event(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = EvaluationService(tmp_path / "evaluations.db", events=events)

    created = service.create_evaluation(
        session_id="session-1",
        decision_id="decision-1",
        artifact_id=None,
        evaluation_type="manual_review",
        status="recorded",
    )

    persisted = service.get_evaluation(created.id)
    assert persisted.id == created.id
    assert persisted.session_id == "session-1"
    assert persisted.decision_id == "decision-1"
    assert persisted.artifact_id is None
    assert persisted.evaluation_type == "manual_review"
    assert persisted.status == "recorded"

    records = events.list_persisted_events(event_type="evaluation_created")
    assert len(records) == 1
    assert records[0].metadata["evaluation_id"] == created.id
    assert records[0].metadata["session_id"] == "session-1"
    assert records[0].metadata["evaluation_type"] == "manual_review"
    assert records[0].metadata["target_type"] is None
    assert records[0].metadata["target_id"] is None


def test_evaluation_artifact_target_snapshot_wins_when_multiple_exist(
    tmp_path,
) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    artifacts = ArtifactService(tmp_path / "artifacts.db")
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    decisions = DecisionRecordService(tmp_path / "decisions.db")
    service = EvaluationService(
        tmp_path / "evaluations.db",
        events=events,
        artifacts=artifacts,
        decisions=decisions,
        sessions=sessions,
    )
    session = sessions.create_session("task-artifact")
    artifact = artifacts.create_artifact_without_event(
        path="reports/outcome.md",
        kind="report",
        task_id=session.task_id,
    )
    decision_id = "decision-artifact"
    with decisions.session_factory() as db:
        decision = DecisionRecordRecord(
            decision_id=decision_id,
            session_id=session.id,
            task_id=session.task_id,
            decision_type="recommendation_selection",
            selected_entity_id="recommendation-1",
            selected_entity_type="planner_recommendation",
            rationale="Selected recommendation",
            created_at=datetime(2026, 6, 16, tzinfo=UTC),
        )
        db.add(decision)
        db.commit()

    evaluation = service.create_evaluation(
        session_id=session.id,
        decision_id=decision_id,
        artifact_id=artifact.id,
        evaluation_type="manual_review",
        status="recorded",
    )
    snapshot = service.get_target_snapshot(evaluation.id)

    assert snapshot.target_type == "artifact"
    assert snapshot.target_id == artifact.id
    assert snapshot.target_summary == "reports/outcome.md"
    assert service.target_snapshot_for(snapshot) == {
        "kind": "report",
        "task_id": session.task_id,
        "proposal_id": None,
    }
    event = events.list_persisted_events(event_type="evaluation_created")[0]
    assert event.metadata["target_type"] == "artifact"
    assert event.metadata["target_id"] == artifact.id


def test_evaluation_decision_target_snapshot_created(tmp_path) -> None:
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    decisions = DecisionRecordService(tmp_path / "decisions.db")
    service = EvaluationService(
        tmp_path / "evaluations.db",
        decisions=decisions,
        sessions=sessions,
    )
    session = sessions.create_session("task-decision")
    decision_id = "decision-only"
    with decisions.session_factory() as db:
        decision = DecisionRecordRecord(
            decision_id=decision_id,
            session_id=session.id,
            task_id=session.task_id,
            decision_type="recommendation_selection",
            selected_entity_id="recommendation-2",
            selected_entity_type="planner_recommendation",
            rationale="Decision-only target",
            created_at=datetime(2026, 6, 16, tzinfo=UTC),
        )
        db.add(decision)
        db.commit()

    evaluation = service.create_evaluation(
        decision_id=decision_id,
        evaluation_type="manual_review",
        status="recorded",
    )
    snapshot = service.get_target_snapshot(evaluation.id)

    assert snapshot.target_type == "decision"
    assert snapshot.target_id == decision_id
    assert snapshot.target_summary == "recommendation_selection"
    assert service.target_snapshot_for(snapshot) == {
        "session_id": session.id,
        "task_id": session.task_id,
        "selected_entity_id": "recommendation-2",
        "selected_entity_type": "planner_recommendation",
    }


def test_evaluation_session_target_snapshot_created(tmp_path) -> None:
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    service = EvaluationService(
        tmp_path / "evaluations.db",
        sessions=sessions,
    )
    session = sessions.create_session("task-session")

    evaluation = service.create_evaluation(
        session_id=session.id,
        evaluation_type="manual_review",
        status="recorded",
    )
    snapshot = service.get_target_snapshot(evaluation.id)

    assert snapshot.target_type == "session"
    assert snapshot.target_id == session.id
    assert snapshot.target_summary == "task-session"
    assert service.target_snapshot_for(snapshot) == {
        "task_id": "task-session",
        "status": "created",
    }


def test_evaluation_rejects_missing_references(tmp_path) -> None:
    service = EvaluationService(tmp_path / "evaluations.db")

    try:
        service.create_evaluation(
            evaluation_type="manual_review",
            status="recorded",
        )
    except Exception as exc:
        assert "At least one reference is required" in str(exc)
    else:
        raise AssertionError("evaluation without references should fail")


def test_evaluation_result_attachment_persists_and_emits_event(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = EvaluationService(tmp_path / "evaluations.db", events=events)
    dimension = service.create_dimension(
        name="Correctness",
        description="Generic correctness signal",
    )
    evaluation = service.create_evaluation(
        session_id="session-1",
        evaluation_type="manual_review",
        status="recorded",
    )

    result = service.add_result(
        evaluation_id=evaluation.id,
        dimension_id=dimension.id,
        score=0.75,
        rationale="Mostly correct",
        metadata={"reviewer": "human"},
    )

    results = service.get_results(evaluation.id)
    assert [record.id for record in results] == [result.id]
    assert results[0].dimension_id == dimension.id
    assert results[0].score == 0.75
    assert service.metadata_for(results[0]) == {"reviewer": "human"}

    records = events.list_persisted_events(
        event_type="evaluation_result_added"
    )
    assert len(records) == 1
    assert records[0].metadata["evaluation_result_id"] == result.id
    assert records[0].metadata["evaluation_id"] == evaluation.id
    assert records[0].metadata["dimension_id"] == dimension.id
    assert records[0].metadata["score"] == 0.75


def test_evaluation_listing_filters_by_reference(tmp_path) -> None:
    service = EvaluationService(tmp_path / "evaluations.db")
    first = service.create_evaluation(
        session_id="session-1",
        evaluation_type="manual_review",
        status="recorded",
    )
    second = service.create_evaluation(
        artifact_id="artifact-1",
        evaluation_type="artifact_review",
        status="draft",
    )

    assert [item.id for item in service.list_evaluations()] == [
        first.id,
        second.id,
    ]
    assert [
        item.id for item in service.list_evaluations(session_id="session-1")
    ] == [first.id]
    assert [
        item.id for item in service.list_evaluations(artifact_id="artifact-1")
    ] == [second.id]


def test_evaluation_api_create_result_get_and_list() -> None:
    client = TestClient(app)
    dimension = client.post(
        "/evaluation-dimensions",
        json={
            "name": "Helpfulness",
            "description": "Generic helpfulness signal",
        },
    ).json()
    created = client.post(
        "/evaluations",
        json={
            "session_id": "session-api",
            "evaluation_type": "manual_review",
            "status": "recorded",
        },
    ).json()

    result = client.post(
        f"/evaluations/{created['id']}/results",
        json={
            "dimension_id": dimension["id"],
            "score": 4.5,
            "rationale": "Useful output",
            "metadata": {"scale": "generic"},
        },
    ).json()

    detail = client.get(f"/evaluations/{created['id']}").json()
    assert detail["id"] == created["id"]
    assert detail["target_snapshot"] is None
    assert detail["results"][0]["id"] == result["id"]
    assert detail["results"][0]["score"] == 4.5

    listed = client.get("/evaluations?session_id=session-api").json()
    assert [item["id"] for item in listed] == [created["id"]]


def test_evaluation_api_exposes_target_snapshot() -> None:
    client = TestClient(app)
    session = runtime_session_service.create_session("task-api-target")
    artifact = artifact_service.create_artifact_without_event(
        path="reports/api-target.md",
        kind="report",
        task_id=session.task_id,
    )

    created = client.post(
        "/evaluations",
        json={
            "session_id": session.id,
            "artifact_id": artifact.id,
            "evaluation_type": "artifact_review",
            "status": "recorded",
        },
    ).json()

    detail = client.get(f"/evaluations/{created['id']}").json()

    assert detail["target_snapshot"] == {
        "evaluation_id": created["id"],
        "target_type": "artifact",
        "target_id": artifact.id,
        "target_summary": "reports/api-target.md",
        "target_metadata": {
            "kind": "report",
            "task_id": session.task_id,
            "proposal_id": None,
        },
        "created_at": created["created_at"],
    }


def test_evaluation_reconstruction_from_events(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    service = EvaluationService(tmp_path / "evaluations.db", events=events)
    dimension = service.create_dimension("Quality", "Generic quality signal")
    evaluation = service.create_evaluation(
        session_id="session-1",
        decision_id="decision-1",
        evaluation_type="manual_review",
        status="recorded",
    )
    result = service.add_result(
        evaluation.id,
        dimension.id,
        1.25,
        "Captured state",
    )
    reconstruction = ReconstructionService(events=EventService(trace_store))

    rebuilt = reconstruction.reconstruct_evaluations(session_id="session-1")

    assert rebuilt["evaluation_count"] == 1
    assert rebuilt["evaluation_counts_by_type"] == {"manual_review": 1}
    assert rebuilt["evaluations"] == [
        {
            "id": evaluation.id,
            "session_id": "session-1",
            "decision_id": "decision-1",
            "artifact_id": None,
            "evaluation_type": "manual_review",
            "status": "recorded",
            "created_at": evaluation.created_at.isoformat(),
            "results": [
                {
                    "evaluation_result_id": result.id,
                    "evaluation_id": evaluation.id,
                    "dimension_id": dimension.id,
                    "score": 1.25,
                    "rationale": "Captured state",
                    "metadata": None,
                    "created_at": result.created_at.isoformat(),
                }
            ],
        }
    ]


def test_runtime_reconstruction_includes_evaluations(tmp_path) -> None:
    trace_store = TraceService(tmp_path / "trace.db")
    events = EventService(trace_store)
    sessions = RuntimeSessionService(tmp_path / "sessions.db")
    session = sessions.create_session("task-1")
    service = RuntimeReconstructionService(
        events=events,
        sessions=sessions,
    )
    created_at = datetime(2026, 6, 16, tzinfo=UTC)
    events.emit_event_sync(
        EventType.EVALUATION_CREATED,
        "Evaluation created",
        metadata={
            "evaluation_id": "evaluation-1",
            "session_id": session.id,
            "evaluation_type": "manual_review",
            "status": "recorded",
            "created_at": created_at.isoformat(),
        },
    )
    events.emit_event_sync(
        EventType.EVALUATION_RESULT_ADDED,
        "Evaluation result added",
        metadata={
            "evaluation_result_id": "result-1",
            "evaluation_id": "evaluation-1",
            "session_id": session.id,
            "dimension_id": "dimension-1",
            "score": 2.0,
            "rationale": "State is reconstructable",
            "created_at": created_at.isoformat(),
        },
    )

    view = service.reconstruct(session.id)

    assert len(view.evaluation_summaries) == 1
    summary = view.evaluation_summaries[0]
    assert summary.evaluation_id == "evaluation-1"
    assert summary.evaluation_type == "manual_review"
    assert summary.status == "recorded"
    assert summary.results[0].evaluation_result_id == "result-1"
    assert summary.results[0].score == 2.0
    assert [
        item.event_type for item in view.timeline
    ] == ["evaluation_created", "evaluation_result_added"]


def test_global_evaluation_service_uses_test_db() -> None:
    created = evaluation_service.create_evaluation(
        session_id="session-fixture",
        evaluation_type="manual_review",
        status="recorded",
    )

    assert evaluation_service.get_evaluation(created.id).id == created.id
    assert event_service.list_persisted_events(
        event_type="evaluation_created"
    )


def test_runtime_evaluation_record_can_be_created_and_retrieved() -> None:
    client = TestClient(app)

    created = client.post(
        "/runtime/evaluations",
        json={
            "session_id": "session-runtime",
            "task_id": "task-runtime",
            "target_type": "decision",
            "target_id": "decision-1",
            "evaluation_type": "governance_review",
            "outcome": "accepted",
            "score": 0.95,
            "evaluator": "governance",
            "rationale": "Decision satisfied runtime criteria.",
            "metadata": {"source": "test"},
        },
    )

    assert created.status_code == 200
    body = created.json()
    assert body["evaluation_id"] == "evaluation-record-1"
    assert body["target_type"] == "decision"
    assert body["target_id"] == "decision-1"
    assert body["outcome"] == "accepted"
    assert body["metadata"] == {"source": "test"}
    assert "created_at" in body

    detail = client.get(
        f"/runtime/evaluations/{body['evaluation_id']}"
    )
    assert detail.status_code == 200
    assert detail.json() == body


def create_runtime_evaluation_record(
    client: TestClient,
    *,
    target_type: str,
    target_id: str,
    evaluation_type: str,
    outcome: str,
) -> dict:
    response = client.post(
        "/runtime/evaluations",
        json={
            "target_type": target_type,
            "target_id": target_id,
            "evaluation_type": evaluation_type,
            "outcome": outcome,
            "evaluator": "governance",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_runtime_evaluation_record_listing() -> None:
    client = TestClient(app)
    first = create_runtime_evaluation_record(
        client,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
    )
    second = create_runtime_evaluation_record(
        client,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
    )

    assert [
        item["evaluation_id"]
        for item in client.get("/runtime/evaluations").json()
    ] == [first["evaluation_id"], second["evaluation_id"]]


def test_runtime_evaluation_record_filter_by_target_type() -> None:
    client = TestClient(app)
    first = create_runtime_evaluation_record(
        client,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
    )
    create_runtime_evaluation_record(
        client,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
    )

    assert [
        item["evaluation_id"]
        for item in client.get(
            "/runtime/evaluations?target_type=artifact"
        ).json()
    ] == [first["evaluation_id"]]


def test_runtime_evaluation_record_filter_by_target_id() -> None:
    client = TestClient(app)
    create_runtime_evaluation_record(
        client,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
    )
    second = create_runtime_evaluation_record(
        client,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
    )

    assert [
        item["evaluation_id"]
        for item in client.get(
            "/runtime/evaluations?target_id=decision-1"
        ).json()
    ] == [second["evaluation_id"]]


def test_runtime_evaluation_record_filter_by_evaluation_type() -> None:
    client = TestClient(app)
    create_runtime_evaluation_record(
        client,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
    )
    second = create_runtime_evaluation_record(
        client,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
    )

    assert [
        item["evaluation_id"]
        for item in client.get(
            "/runtime/evaluations?evaluation_type=safety_review"
        ).json()
    ] == [second["evaluation_id"]]


def test_runtime_evaluation_record_filter_by_outcome() -> None:
    client = TestClient(app)
    first = create_runtime_evaluation_record(
        client,
        target_type="artifact",
        target_id="artifact-1",
        evaluation_type="quality_review",
        outcome="success",
    )
    create_runtime_evaluation_record(
        client,
        target_type="decision",
        target_id="decision-1",
        evaluation_type="safety_review",
        outcome="failure",
    )

    assert [
        item["evaluation_id"]
        for item in client.get(
            "/runtime/evaluations?outcome=success"
        ).json()
    ] == [first["evaluation_id"]]


def test_runtime_evaluation_record_missing_record_returns_404() -> None:
    response = TestClient(app).get(
        "/runtime/evaluations/missing-evaluation"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Evaluation record not found: missing-evaluation"
    }


def test_runtime_evaluation_record_rejects_invalid_target_type() -> None:
    response = TestClient(app).post(
        "/runtime/evaluations",
        json={
            "target_type": "planner_authority",
            "target_id": "target-1",
            "evaluation_type": "governance_review",
            "outcome": "success",
            "evaluator": "governance",
        },
    )

    assert response.status_code == 422


def test_runtime_evaluation_record_rejects_invalid_outcome() -> None:
    response = TestClient(app).post(
        "/runtime/evaluations",
        json={
            "target_type": "runtime_session",
            "target_id": "session-1",
            "evaluation_type": "governance_review",
            "outcome": "planner_override",
            "evaluator": "governance",
        },
    )

    assert response.status_code == 422
